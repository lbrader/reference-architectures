#!/bin/bash


CRUMB=$(curl -s 'http://localhost:8080/crumbIssuer/api/xml?xpath=concat(//crumbRequestField,":",//crumb)')

curl -H $CRUMB -X POST 'http://localhost:8080/credentials/store/system/domain/_/createCredentials' \
--data-urlencode 'json={
  "": "0",
  "credentials": {
    "scope": "GLOBAL",
    "id": "{{ github_credentials_id }}",
    "username": "{{ github_username }}",
    "password": "{{ github_token }}",
    "description": "jenkins github credentials",
    "$class": "com.cloudbees.plugins.credentials.impl.UsernamePasswordCredentialsImpl"
  }
}'

curl -H $CRUMB -X POST 'http://localhost:8080/credentials/store/system/domain/_/createCredentials' \
--data-urlencode 'json={
  "": "0",
  "credentials": {
    "scope": "GLOBAL",
    "id": "{{ jenkins_vm_credentials_id }}",
    "username": "{{ jenkins_vm_username }}",
    "password": "{{ jenkins_vm_password }}",
    "description": "jenkins vm credentials",
    "$class": "com.cloudbees.plugins.credentials.impl.UsernamePasswordCredentialsImpl"
  }
}'


curl -H $CRUMB -X POST 'http://localhost:8080/credentials/store/system/domain/_/createCredentials' \
--data-urlencode 'json={
"": "2",
"credentials": {
  "scope": "GLOBAL",
  "id": "{{ azure_credentials_id }}",
  "description": "jenkins_azure_credentials",
  "subscriptionId": "{{ jenkins_subscriptionId }}",
  "clientId": "{{ jenkins_clientId }}",
  "clientSecret": "{{ jenkins_clientSecret }}",
  "oauth2TokenEndpoint": "https://login.windows.net/{{ jenkins_tenant }}",
  "serviceManagementURL": "https://management.core.windows.net/",
  "tenant": "{{ jenkins_tenant }}",
  "authenticationEndpoint": "https://login.microsoftonline.com/",
  "resourceManagerEndpoint": "https://management.azure.com/",
  "graphEndpoint": "https://graph.windows.net/",
  "$class": "com.microsoft.azure.util.AzureCredentials"
}
}'

curl -H $CRUMB -X POST 'http://localhost:8080/credentials/store/system/domain/_/createCredentials' \
--data-urlencode 'json={
"": "2",
"credentials": {
  "scope": "GLOBAL",
  "id": "{{ azure_credentials_id }}_dev",
  "description": "jenkins_azure_credentials",
  "subscriptionId": "{{ dev_subscriptionId }}",
  "clientId": "{{ dev_clientId }}",
  "clientSecret": "{{ dev_clientSecret }}",
  "oauth2TokenEndpoint": "https://login.windows.net/{{ dev_tenant }}",
  "serviceManagementURL": "https://management.core.windows.net/",
  "tenant": "{{ dev_tenant }}",
  "authenticationEndpoint": "https://login.microsoftonline.com/",
  "resourceManagerEndpoint": "https://management.azure.com/",
  "graphEndpoint": "https://graph.windows.net/",
  "$class": "com.microsoft.azure.util.AzureCredentials"
}
}'

curl -H $CRUMB -X POST 'http://localhost:8080/credentials/store/system/domain/_/createCredentials' \
--data-urlencode 'json={
"": "2",
"credentials": {
  "scope": "GLOBAL",
  "id": "{{ azure_credentials_id }}_test",
  "description": "jenkins_azure_credentials",
  "subscriptionId": "{{ test_subscriptionId }}",
  "clientId": "{{ test_clientId }}",
  "clientSecret": "{{ test_clientSecret }}",
  "oauth2TokenEndpoint": "https://login.windows.net/{{ test_tenant }}",
  "serviceManagementURL": "https://management.core.windows.net/",
  "tenant": "{{ test_tenant }}",
  "authenticationEndpoint": "https://login.microsoftonline.com/",
  "resourceManagerEndpoint": "https://management.azure.com/",
  "graphEndpoint": "https://graph.windows.net/",
  "$class": "com.microsoft.azure.util.AzureCredentials"
}
}'

curl -H $CRUMB -X POST 'http://localhost:8080/credentials/store/system/domain/_/createCredentials' \
--data-urlencode 'json={
"": "2",
"credentials": {
  "scope": "GLOBAL",
  "id": "{{ azure_credentials_id }}_master",
  "description": "jenkins_azure_credentials",
  "subscriptionId": "{{ prod_subscriptionId }}",
  "clientId": "{{ prod_clientId }}",
  "clientSecret": "{{ prod_clientSecret }}",
  "oauth2TokenEndpoint": "https://login.windows.net/{{ prod_tenant }}",
  "serviceManagementURL": "https://management.core.windows.net/",
  "tenant": "{{ prod_tenant }}",
  "authenticationEndpoint": "https://login.microsoftonline.com/",
  "resourceManagerEndpoint": "https://management.azure.com/",
  "graphEndpoint": "https://graph.windows.net/",
  "$class": "com.microsoft.azure.util.AzureCredentials"
}
}'

#curl -H $CRUMB --data-urlencode "script=$(<./manage_jenkins_plugin_mailer.groovy)" http://localhost:8080/scriptText
#curl -H $CRUMB --data-urlencode "script=$(<./file_credentials.groovy)" http://localhost:8080/scriptText

echo "Credentials creation completed"