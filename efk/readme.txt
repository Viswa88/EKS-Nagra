efk directory taken from kubespray git repo and adapted to our needs:
- updated efk stack version - according to kubespray's pull request: https://github.com/kubernetes-incubator/kubespray/pull/2763
- updated elasticsearch version to 6.2.4 and kibana to 6.2.4, including logtrail plugin (https://github.com/sivasamyk/logtrail)
- usage of persistent volume for data storage
- Added increased ping and zen timeout values to worj around CICD issue 