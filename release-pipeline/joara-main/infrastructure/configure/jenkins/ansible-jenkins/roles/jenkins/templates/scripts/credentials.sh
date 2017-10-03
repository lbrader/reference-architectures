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
  "subscriptionId": "{{ subscriptionId }}",
  "clientId": "{{ clientId }}",
  "clientSecret": "{{ clientSecret }}",
  "oauth2TokenEndpoint": "https://login.windows.net/{{ tenant }}",
  "serviceManagementURL": "https://management.core.windows.net/",
  "tenant": "{{ tenant }}",
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
  "subscriptionId": "{{ subscriptionId }}",
  "clientId": "{{ clientId }}",
  "clientSecret": "{{ clientSecret }}",
  "oauth2TokenEndpoint": "https://login.windows.net/{{ tenant }}",
  "serviceManagementURL": "https://management.core.windows.net/",
  "tenant": "{{ tenant }}",
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
  "subscriptionId": "{{ subscriptionId }}",
  "clientId": "{{ clientId }}",
  "clientSecret": "{{ clientSecret }}",
  "oauth2TokenEndpoint": "https://login.windows.net/{{ tenant }}",
  "serviceManagementURL": "https://management.core.windows.net/",
  "tenant": "{{ tenant }}",
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
  "subscriptionId": "{{ subscriptionId }}",
  "clientId": "{{ clientId }}",
  "clientSecret": "{{ clientSecret }}",
  "oauth2TokenEndpoint": "https://login.windows.net/{{ tenant }}",
  "serviceManagementURL": "https://management.core.windows.net/",
  "tenant": "{{ tenant }}",
  "authenticationEndpoint": "https://login.microsoftonline.com/",
  "resourceManagerEndpoint": "https://management.azure.com/",
  "graphEndpoint": "https://graph.windows.net/",
  "$class": "com.microsoft.azure.util.AzureCredentials"
}
}'

#curl -H $CRUMB --data-urlencode "script=$(<./manage_jenkins_plugin_mailer.groovy)" http://localhost:8080/scriptText
#curl -H $CRUMB --data-urlencode "script=$(<./file_credentials.groovy)" http://localhost:8080/scriptText

echo "Credentials creation completed"