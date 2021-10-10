#!/usr/bin/env python

import os
import argparse
import json
import yaml
import sys

try:
  import boto3
except:
  print("Clearly you don't have AWS support")
  sys.exit(1)

class SearchInstances(object):

  def __init__(self):
    self.vpc_id = None
    self.parse_args()
    self.load_config()
    self.init_hosts_dict()
    self.search_vpc_availability_zone()


    tries = 3
    for i in range(tries):
      try:
        self.search_instances()
      except:
        if i < tries - 1:
          continue
        else:
          raise
      break

    if self.args.list:
      print json.dumps(self.hosts, sort_keys=True, indent=2)
    if self.args.host:
      data = {}
      print json.dumps(self.hosts['_meta']['hostvars'][self.args.host], indent=2)

  def init_hosts_dict(self):
    self.hosts = {}
    self.hosts['_meta'] = { 'hostvars': {} }
    self.hosts[self.config['platform']] = {'children':['ubuntu'], 'hosts': []}
    self.hosts['ubuntu'] = {'children': ['kubernetes', 'databases','gateways','tableau','sni_router']}
    self.hosts['kubernetes'] = {'children':['masters','workers']}
    self.hosts['databases'] = {'children':['mongodb','neo4j','rabbitmq','cassandra','elasticsearch','solr','zookeeper','keycloak']}
    self.hosts['dockers'] = {'children':['databases','gateways', 'tableau', 'sni_router']}
    self.hosts['sni_router'] = {'hosts': []}
    self.hosts['gateways'] = {'hosts': []}

  def parse_args(self):
    ##Support --list and --host flags. We largely ignore the host one.
    parser = argparse.ArgumentParser()
    parser.add_argument('--list', action='store_true', default=True, help='List instances')
    parser.add_argument('--host', action='store', help='Get all the variables about a specific instance')
    self.args = parser.parse_args()

  def check_duplicate_keys_in_dict(self, dct, new_dict):
    for k in new_dict:
      if k in dct.keys():
        sys.stderr.write("Found duplicate key '{}' in configuration files which is not allowed!".format(k))
        sys.exit(0)

  def dict_merge(self, dct, merge_dct):
    """ Recursive dict merge. Inspired by :meth:``dict.update()``, instead of
    updating only top-level keys, dict_merge recurses down into dicts nested
    to an arbitrary depth, updating keys. The ``merge_dct`` is merged into
    ``dct``.
    :param dct: dict onto which the merge is executed
    :param merge_dct: dct merged into dct
    :return: None
    """
    for k, v in merge_dct.iteritems():
      if k in dct and isinstance(dct[k], dict):
        self.dict_merge(dct[k], merge_dct[k])
      else:
        dct[k] = merge_dct[k]

  def load_config(self):
    config_file = os.environ['CONFIG_FILE']

    self.config = None
    for file in config_file.split(','):
      with open(file, 'r') as stream:
        try:
          yaml_doc = yaml.load(stream, Loader=yaml.FullLoader)
          if self.config:
            self.check_duplicate_keys_in_dict(self.config, yaml_doc)
            self.dict_merge(self.config, yaml_doc)
          else:
            self.config = yaml_doc
        except yaml.YAMLError as exc:
          print(exc)

    if 'aws_access_key' in self.config:
      os.environ['AWS_ACCESS_KEY_ID'] = self.config['aws_access_key']
    if 'aws_secret_key' in self.config:
      os.environ['AWS_SECRET_ACCESS_KEY'] = self.config['aws_secret_key']
    if 'aws_region' in self.config:
      os.environ['AWS_DEFAULT_REGION'] = self.config['aws_region']

  # If a VPC already exists then find the availability_zone that has been used to make the first deployment
  def search_vpc_availability_zone(self):
    ec2 = boto3.resource('ec2')
    ec2_client = boto3.client('ec2')

    zones_reponse = ec2_client.describe_availability_zones(Filters=[{
            'Name': 'region-name',
            'Values': [self.config['aws_region']]
        }
    ])
    self.availability_zone_list = [az['ZoneName'] for az in zones_reponse['AvailabilityZones']]
    self.availability_zone_list.sort()

    self.subnet_by_name_by_az = {}
    self.subnet_by_id = {}

    filters = [{'Name':'tag:Name', 'Values': [self.config['vpc_name']]}]
    vpcs = list(ec2.vpcs.filter(Filters=filters))

    if vpcs:
      self.vpc_id = vpcs[0].vpc_id
      all_vpc_subnets = list(vpcs[0].subnets.all())
      az_set = set()
      if all_vpc_subnets:
        for subnet in all_vpc_subnets:
          name = [x['Value'] for x in subnet.tags if x['Key'] == 'Name'][0]
          if name not in self.subnet_by_name_by_az:
            self.subnet_by_name_by_az[name] = {}
          self.subnet_by_name_by_az[name][subnet.availability_zone] = subnet.id
          self.subnet_by_id[subnet.id] = {'name':name, 'availability_zone':subnet.availability_zone}

          az_set.add(subnet.availability_zone)
          if subnet.cidr_block == '10.0.1.0/24':
            main_availability_zone = subnet.availability_zone

    #if not AZ was found, the first is used as "main"
    try:
      self.vpc_availability_zone = main_availability_zone
    except NameError:
      self.vpc_availability_zone = self.availability_zone_list[0]

    #remove the "main" AZ from the list
    self.availability_zone_list.remove(self.vpc_availability_zone)
    #keep only the 2 first AZs from the list as "extra" AZs
    self.availability_zone_list = self.availability_zone_list[0:2]


    self.eip_subnet_allocations = []
    self.lb_eips = []

    #Find alrady tagged EIPs
    tagged_eips =  ec2_client.describe_addresses(Filters=[
          {'Name': 'tag:Name', 'Values': [self.config['vpc_name'] + '_eip_nlb']},
          {'Name': 'tag:environment', 'Values': [self.config['vpc_name']]}
    ])
    if tagged_eips:
      self.lb_eips = tagged_eips['Addresses']

    #Work on EIPs only if subnets already exists
    if self.subnet_by_id:
      allocated_eips = []
      not_allocated_eips = []
      free_zones = [self.vpc_availability_zone] + self.availability_zone_list

      for eip in self.lb_eips:
        if 'NetworkInterfaceId' in eip:
          nic = ec2_client.describe_network_interfaces(NetworkInterfaceIds=[eip['NetworkInterfaceId']])
          az = nic['NetworkInterfaces'][0]['AvailabilityZone']
          free_zones.remove(az)
          self.eip_subnet_allocations.append({'SubnetId':nic['NetworkInterfaces'][0]['SubnetId'], 'AllocationId':eip['AllocationId'], 'AvailabilityZone':az})
        else:
          not_allocated_eips.append(eip)

      if 'public' in self.subnet_by_name_by_az:
        for num, not_allocated_eip in enumerate(not_allocated_eips):
          az = free_zones[num]
          if az in self.subnet_by_name_by_az['public']:
            self.eip_subnet_allocations.append({'SubnetId':self.subnet_by_name_by_az['public'][az] , 'AllocationId':not_allocated_eip['AllocationId'], 'AvailabilityZone':az})


  def search_instances(self):
    ec2 = boto3.resource('ec2')
    ec2_client = boto3.client('ec2')

    # get the primary gateway public IP from config file
    primary_gateway_ip = self.config["aws_gateway_eip"]
    gateway_ip = ''
    gateway_private_ip = ''

    #Search for the gateway public IP
    gateway = ec2.instances.filter(Filters=[{'Name': 'tag:Name', 'Values': ['gateway']}, {'Name': 'instance-state-name', 'Values': ['running']}, {'Name': 'tag:environment', 'Values': [self.config['vpc_name']]}])
    for gtw in gateway:
      gateway_ip = gtw.public_ip_address
      gateway_private_ip = gtw.private_ip_address

    sni_routers = ec2.instances.filter(Filters=[{'Name': 'tag:role', 'Values': ['sni_router']}, {'Name': 'instance-state-name', 'Values': ['running']}, {'Name': 'tag:environment', 'Values': [self.config['vpc_name']]}])
    for instance in sni_routers:
      tags = {item['Key']: item['Value'] for item in instance.tags }
      self.hosts['sni_router']['hosts'].append(tags['Name'])
      self.hosts['sni_router']['vars'] = {'role': tags['role']}
      self.hosts['_meta']['hostvars'][tags['Name']] = {
        'gateway_ip': gateway_ip,
        'gateway_private_ip': gateway_private_ip,
        'ansible_host': instance.private_ip_address,
        'ansible_ssh_private_key_file': self.config['ssh_private_key_vpc_file'],
        'shared': True
      }
      self.hosts['_meta']['hostvars'][tags['Name']]['ansible_ssh_common_args'] = "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null  -o ProxyCommand='ssh -W %h:%p -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null  -o ProxyCommand=\"ssh -W %%h:%p -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ubuntu@"+primary_gateway_ip+" -i "+self.config['ssh_private_key_vpc_file']+"\" ubuntu@"+gateway_ip+" -i "+self.config['ssh_private_key_vpc_file']+"'"

    #### localhost ####
    self.hosts['aws']['hosts'].append('localhost')
    self.hosts['_meta']['hostvars']['localhost'] = {}
    self.hosts['_meta']['hostvars']['localhost']['ansible_connection'] = 'local'
    self.hosts['_meta']['hostvars']['localhost']['ansible_python_interpreter'] = '/usr/bin/python'
    self.hosts['_meta']['hostvars']['localhost']['gateway_ip'] = gateway_ip
    self.hosts['_meta']['hostvars']['localhost']['availability_zone'] = self.vpc_availability_zone
    self.hosts['_meta']['hostvars']['localhost']['availability_zone_list'] = self.availability_zone_list
    self.hosts['_meta']['hostvars']['localhost']['subnet_by_name_by_az'] = self.subnet_by_name_by_az
    self.hosts['_meta']['hostvars']['localhost']['subnet_by_id'] = self.subnet_by_id
    self.hosts['_meta']['hostvars']['localhost']['eip_subnet_allocations'] = self.eip_subnet_allocations
    self.hosts['_meta']['hostvars']['localhost']['lb_eips'] = self.lb_eips

    if self.vpc_id:
      self.hosts['_meta']['hostvars']['localhost']['vpc_id'] = self.vpc_id

    #### gateway ####
    self.hosts['gateways']['hosts'] = ['gateway']
    self.hosts['_meta']['hostvars']['gateway'] = {}
    self.hosts['_meta']['hostvars']['gateway']['availability_zone'] = self.vpc_availability_zone
    self.hosts['_meta']['hostvars']['gateway']['availability_zone_list'] = self.availability_zone_list
    self.hosts['_meta']['hostvars']['gateway']['ansible_ssh_private_key_file'] = self.config['ssh_private_key_vpc_file']
    self.hosts['_meta']['hostvars']['gateway']['shared'] = True
    self.hosts['_meta']['hostvars']['gateway']['ansible_ssh_common_args'] = "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ProxyCommand='ssh -W %h:%p -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null  ubuntu@"+primary_gateway_ip+" -i "+self.config['ssh_private_key_vpc_file']+"'"

    if gateway_ip:
      self.hosts['_meta']['hostvars']['gateway']['ansible_host'] = gateway_ip
      self.hosts['_meta']['hostvars']['gateway']['gateway_ip'] = gateway_ip
      self.hosts['_meta']['hostvars']['gateway']['gateway_private_ip'] = gateway_private_ip
      self.hosts['_meta']['hostvars']['gateway']['vpc_id'] = self.vpc_id


    env_private_key_file = '~/.ssh/id_rsa'
    if 'ssh_private_key_env_file' in self.config and self.config['ssh_private_key_env_file']:
      env_private_key_file = self.config['ssh_private_key_env_file']

    # This part must not be executed in case of a VPC deployment only (no environment_name parameter)
    if 'environment_name' in self.config.keys():
      for instance in ec2.instances.all():

        # Filter instances that are shutting down or are terminated
        if instance.state['Name'] in ['shutting-down', 'terminated'] or not instance.tags:
          continue

        tags = {item['Key']: item['Value'] for item in instance.tags}

        # Filter instances that do not have the environment tag with the correct value
        if 'environment' not in tags or tags['environment'] != (self.config['environment_name'] or self.config['vpc_name']):
          continue

        # Converts the tags value from string to array and remove leading and trailing spaces
        if 'role' in tags:
          tags['role'] = [item.strip() for item in tags['role'].split(',')]
        else:
          tags['role'] = []

        # If the instances has no "Name" tag, its private DNS name is used instead
        name = tags['Name'] if 'Name' in tags else instance.private_dns_name
        # Create a group for each instance role
        for role in tags['role']:
          if role not in self.hosts.keys():
            self.hosts[role] = {"hosts": [], "vars": {}, "children": []}
          self.hosts[role]['hosts'].append(name)
          self.hosts[role]['vars'] = {'role': role}

        # Add hostvars for the current instance
        self.hosts['_meta']['hostvars'][name] = {
          'gateway_ip': gateway_ip,
          'gateway_private_ip': gateway_private_ip,
          'ansible_host': instance.private_ip_address,
          'availability_zone': self.vpc_availability_zone,
          'availability_zone_list': self.availability_zone_list,
          'instance_id': instance.instance_id,
          'shared': False,
          'ansible_python_interpreter': '/usr/bin/python3',
          'ansible_ssh_common_args': "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null  -o ProxyCommand='ssh -W %h:%p -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null  -o ProxyCommand=\"ssh -W %%h:%p -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ubuntu@"+primary_gateway_ip+" -i "+self.config['ssh_private_key_vpc_file']+"\" ubuntu@"+gateway_ip+" -i "+self.config['ssh_private_key_vpc_file']+"'",
          'ansible_ssh_private_key_file': env_private_key_file
        }

        #Workers instance do not user Ubuntu, the use AWS Linux where the user is ec2-user
        if 'workers' in tags['role']:
          self.hosts['_meta']['hostvars'][name]['ansible_ssh_user'] = 'ec2-user'
          self.hosts['_meta']['hostvars'][name]['ansible_python_interpreter'] = '/usr/bin/python'

        if 'eks_goldenami_id' in self.config:
          self.hosts['_meta']['hostvars'][name]['ansible_ssh_user'] = 'ubuntu'

        # If any of the instance's role is a database role, the instance is a database
        if any((True for x in tags['role'] if x in self.hosts['databases']['children'])):
          eni_result = ec2_client.describe_network_interfaces(Filters=[{'Name':'attachment.instance-id','Values':[instance.instance_id]}])
          for eni in eni_result['NetworkInterfaces']:
            for tag in eni['TagSet']:
              if tag['Key'] == 'Name' and tag['Value'].endswith('-db'):
                self.hosts['_meta']['hostvars'][name]['db_nic_private_ip'] = eni['PrivateIpAddress']
                self.hosts['_meta']['hostvars'][name]['db_nic_mac'] = eni['MacAddress']

if __name__ == "__main__":
  SearchInstances()
