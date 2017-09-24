#!/bin/bash


#set -ex

Color_Off='\033[0m'       # Text Reset
Red='\033[0;31m'          # Red
Green='\033[0;32m'        # Green
BRed='\033[1;31m'         # Red
BGreen='\033[1;32m'       # Green

run_command () {
   success_echo "${1}"
   eval $1
   if [ $? -ne 0 ]; then
    failure_echo "${TO_DATACENTER} was not successful"
    exit 1
   fi
}

success_echo () {

   echo -e "${BGreen}${1}${Color_Off}"
}

failure_echo () {

   echo -e "${BRed}${1}${Color_Off}"
}


TO_DATACENTER="$1"
IMAGE_NAME="$2"

if [ "$TO_DATACENTER" == "master" ]; then
  TO_DATACENTER='prod'
fi


export PATH=/var/lib/jenkins/conda/bin:$PATH
source activate vjoaraapp3


if [ -z "$TO_DATACENTER" ] ; then
    success_echo "\$TO_DATACENTER was not set"
    exit 1
fi

pre_setup_env ()
{
    success_echo "Installing JOARA"
    CMD="pip install --editable joara-app-provision"
    run_command "${CMD}"

}

image_default_action ()
{
    image_action="build,push,deploy"
    success_echo "Docker Image build,push, deploy"
    run_command "${CMD}"
    IFS=', ' read -r -a array <<< "$image_action"
    for action in "${array[@]}"
    do
        CMD="joara -d $TO_DATACENTER image --images $IMAGE_NAME --task ${action} --verbose"
        run_command "${CMD}"
    done

}

CMD="echo $PWD"
run_command "${CMD}"

CMD="ls -la"
run_command "${CMD}"

CMD="export AZURE_SUBSCRIPTION_ID=$AZURE_SUBSCRIPTION_ID;export AZURE_CLIENT_ID=$AZURE_CLIENT_ID;export AZURE_CLIENT_SECRET=$AZURE_CLIENT_SECRET;export AZURE_TENANT_ID=$AZURE_TENANT_ID"
run_command "${CMD}"

pre_setup_env

if [[ "$TO_DATACENTER" == "dev" ]]; then
  image_default_action
elif [[ "$TO_DATACENTER" == "test" ]]; then
  CMD="joara -d $TO_DATACENTER syncimage --group image --task copy --source dev --verbose"
  run_command "${CMD}"
elif [[ "$TO_DATACENTER" == "prod" ]]; then
  CMD="joara -d $TO_DATACENTER syncimage --group image --task copy --source test --verbose"
  run_command "${CMD}"
else
    failure_echo "!!!! No environment matched !!!!"
fi



success_echo "Deleting logs directory"
CMD="rm -rf logs"
run_command "${CMD}"

exit 0