@Library('jenkins-library') _
String configFile
pipeline {
    parameters {
        booleanParam(defaultValue: true, description: "RUN_TEARDOWN: Run teardown will delete everything that was previously created. If this is selected RUN_INFRA and RUN_K8S will need to be enabled too", name: 'RUN_TEARDOWN')
        booleanParam(defaultValue: true, description: 'RUN_INFRA: Create the AWS infrastructure. Will need to be enabled if teardown ran', name: 'RUN_INFRA')
        booleanParam(defaultValue: true, description: 'RUN_K8S: Deploy a K8s cluster. Will need to be enabled if teardown ran', name: 'RUN_K8S')
        booleanParam(defaultValue: true, description: 'RUN_APPLICATION:  Install the OPF3 Application stack', name: 'RUN_APPLICATION')
        booleanParam(defaultValue: true, description: 'RUN_VALIDATION: Validate the OPF3 environment – health check on application endpoints', name: 'RUN_VALIDATION')		
		string(defaultValue: '985948', description: 'Playbook changelist number', name: 'CHANGELIST_NUMBER')
		booleanParam(defaultValue: false, description: 'Use modules version file to re-deploy certain modules. Will need only RUN_APPLICATION and RUN_VALIDATION to be enabled and rest disabled', name: 'USE_VERSION_FILE')
		text(defaultValue: """## PRM references
kss: "https://<server>/opf3demo/prm/cks-ws-keyRetrieval/key"
hwprm: "https://<server>/opf3demo/prm/hes-ws-onlineHardwareCredentials/OnlineHardwareCredentials"
swprm: "https://<server>/opf3demo/prm/sls-softwarelicense-WS/SoftwareEntitlementV2"
 
## Uncomment the repository URLs below if you don't want to deploy the default baseline.
  
## File repository
# module_file_repository_url: "https://uex-repo.hq.k.grp/opf-gen-local"
 
## Docker registries
# module_docker_registry_url: "opf-dkr-local.uex-repo.hq.k.grp"
 
# bcm service e.g.: ""
bcm_version: "1.5.2"
 
# cpm service
cpm_version: "5.9.5"
 
# goc service
goc_version: "1.0.6"
 
# uam service
uam_version: "1.0.1.40"
 
# caa service
caa_version: "1.0.0"
 
# adm service
adm_version: "17.48STD0"
 
# rmg service
rmg_version: "1.0.6"
 
# ias service
ias_version: "1.0.6"
 
# agw service
agw_version: "1.0.11"
 
# cds service
cds_version: "1.0.10"
 
# opui service
opui_version: "2.2.3"
 
# mdrm service
mdrm_version: "1.12.3"
 
# cdg service
cdg_version: "4.0.0.2365"
 
# pmg service
pmg_version: "1.0.1.960"
 
# cim-nis service
cim_nis_version: "1.9.5.672"
 
# cex-seac service
cex_seac_version: "1.0.0.20"
 
# cwm service
cwm_version: "1.6.2.475"
 
# metadataserver service
# As MDS requires multiple Docker images (that can have different version numbers) we list them all.
# The values must be consistent with the content of the K8s configuration file
metadataserver_version: "1.0.1.40"
metadataserver_etcd_config_init_image_tag: "1.0.7"
metadataserver_image_tag: "1.0.1.40"
 
 
# services_to_deploy
# ------------------
#
# list of services to deploy. Used for limiting the playbook to a specific list of services for updating the services that have been already deployed.
#
# example:
#
# services_to_deploy:
#   - http_router
#   - bcm
#   - cpm
#   - cwm""", description: 'Module version file', name: 'MODULE_VERSION_FILE')
    }
    environment{
        ANSIBLE_TIMEOUT=30
        ANSIBLE_SSH_ARGS= '-o ControlMaster=auto -o ControlPersist=30m -o ConnectionAttempts=100 -o UserKnownHostsFile=/dev/null' 
        BOTO_USE_ENDPOINT_HEURISTICS=true
        ANSIBLE_SSH_RETRIES=10        
    }
    
    agent { label 'build-docker-03' }
    stages {
        stage('Checkout SCM'){
            steps{
                script{
                configFile =  "opf3/tenants/"+"${env.JOB_NAME}".replace("/","_") + ".yaml"
                // Define the mapping as a variable (veiw)
                String view = """//service-platform/service-environment/ansible/opf3/... //jenkins-${NODE_NAME}-${JOB_NAME}/opf3/...""".stripMargin()
                String name = "jenkins-${env.NODE_NAME}-${env.JOB_NAME}"
                // Checkout the code provide the mapping as a parameter
                //new com.nagra.uex.jenkins.P4Scm(this).p4Checkout("p4-corp", view)
                checkout([$class: 'PerforceScm', credential: "p4-corp", populate: [$class: 'AutoCleanImpl', delete: true, modtime: false, parallel: [enable: false, minbytes: '1024', minfiles: '1', path: '/usr/local/bin/p4', threads: '4'], pin: "${params.CHANGELIST_NUMBER}", quiet: true, replace: true], workspace: [$class: 'ManualWorkspaceImpl', charset: 'none', name: "${name}", pinHost: false, spec: [allwrite: true, clobber: false, compress: false, line: 'LOCAL', locked: false, modtime: false, rmdir: false, streamName: '', view: "${view}"]]])
                sh """sed -i '/create_primary/d' opf3/playbooks/nagra/infra.yaml"""    
                writeFile file:"/home/jenkins/module_version-1.yaml",text:"${params.MODULE_VERSION_FILE}"
                }
            }
        }
        stage('Destroy') {
                when{
                        expression{params.RUN_TEARDOWN ==true}
                }
                environment { 
                       CONFIG_FILE="$configFile"
                }
            steps {
              script {
                  
                ansiblePlaybook extras: """-e @"$configFile" -vvv""", installation: 'Ansible', inventory: 'opf3/inventories/nagra/dev.yaml', playbook: 'opf3/playbooks/nagra/teardown.yaml'
              }
            }
        }
        stage('Deployment[Infra]') {
              when{
                        expression{params.RUN_INFRA ==true}
                }
                environment { 
                       CONFIG_FILE="$configFile"
                }
            steps {
                    script {
                        //Infrastructure playbook
                        ansiblePlaybook extras: """-e @"$configFile" -vvv""", installation: 'Ansible', inventory: 'opf3/inventories/nagra/dev.yaml', playbook: 'opf3/playbooks/nagra/infra.yaml'
                    }
            }
        }
        stage('Deployment[k8]'){
             when{
                        expression{params.RUN_K8S ==true}
                }
                environment { 
                       CONFIG_FILE="$configFile"
                }
            steps{
                script{
                    //Kubernetes playbook
                    ansiblePlaybook become: true, extras: """-e @"$configFile" -vvv""", installation: 'Ansible', inventory: 'opf3/inventories/kubespray/inventory.py', playbook: 'opf3/playbooks/kubespray/cluster.yml'
                }
            }
        }
        stage('Deployment[Application]'){
           when{
                    expression{params.RUN_APPLICATION ==true}

                }
                environment { 
                       CONFIG_FILE="$configFile"
                }
            steps{
                script{                        
                        //new com.nagra.uex.jenkins.Utils(this).createYamlByLatestVersion('/home/jenkins/aws_yaml/module_version.yaml','opf3/inventories/nagra/group_vars/all.yaml')
                        if(params.USE_VERSION_FILE == true){
                            ansiblePlaybook extras: """-e @"$configFile" -e kss="https://ott.nagra.com/opf3demo/prm/cks-ws-keyRetrieval/key" -e swprm="https://ott.nagra.com/opf3demo/prm/sls-softwarelicense-WS/SoftwareEntitlementV2" -e hwprm="https://ott.nagra.com/opf3demo/prm/hes-ws-onlineHardwareCredentials/OnlineHardwareCredentials" -e @"/home/jenkins/module_version-1.yaml" -vvv""", installation: 'Ansible', inventory: 'opf3/inventories/nagra/dev.yaml', playbook: 'opf3/playbooks/nagra/application.yaml'    
                        }else
                        {
                            //Application playbook
                            ansiblePlaybook extras: """-e @"$configFile" -e kss="https://ott.nagra.com/opf3demo/prm/cks-ws-keyRetrieval/key" -e swprm="https://ott.nagra.com/opf3demo/prm/sls-softwarelicense-WS/SoftwareEntitlementV2" -e hwprm="https://ott.nagra.com/opf3demo/prm/hes-ws-onlineHardwareCredentials/OnlineHardwareCredentials" -vvv""", installation: 'Ansible', inventory: 'opf3/inventories/nagra/dev.yaml', playbook: 'opf3/playbooks/nagra/application.yaml'    
                        }                        
                }
            }
        }
        
        stage('Validation'){
             when{
                    expression{params.RUN_VALIDATION ==true}

                }
                environment { 
                       CONFIG_FILE="$configFile"
                }
            steps {
                    script {
                        sleep(300)
                        //new com.nagra.uex.jenkins.Utils(this).createYamlByLatestVersion('/home/jenkins/aws_yaml/module_version.yaml','opf3/inventories/nagra/group_vars/all.yaml')
                        //ansiblePlaybook extras: '-e "@${params.CONFIG_FILE}" -e "@/home/jenkins/aws_yaml/module_version.yaml" -vvv', installation: 'Ansible', inventory: 'opf3/inventories/nagra/dev.yaml', playbook: 'opf3/playbooks/nagra/validation.yaml'
                        if(params.USE_VERSION_FILE == true){
                            ansiblePlaybook extras: """-e @"$configFile" -e @"/home/jenkins/module_version-1.yaml" -vvv""", installation: 'Ansible', inventory: 'opf3/inventories/nagra/dev.yaml', playbook: 'opf3/playbooks/nagra/validation.yaml'
                            
                        }else{
                            ansiblePlaybook extras: """-e @"$configFile" -vvv""", installation: 'Ansible', inventory: 'opf3/inventories/nagra/dev.yaml', playbook: 'opf3/playbooks/nagra/validation.yaml'    
                        }                       
                    }
            }
        }
    }
    post {
        always {
            script {
                //new com.nagra.uex.jenkins.BugReport(this).checkAndCreateJiraIssue()
                new com.nagra.uex.jenkins.ChatOps(this).sendNotification('sre')
            }
        }
    }
}