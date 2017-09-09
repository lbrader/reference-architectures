# JOARA


## Code Details

1. **Infrastructure** - Provisiong of Infrastructure ARM templates, configuring jenkins and docker images
2. **Infrastructure/provisioning** - Provisioning Azure resources
3. **Infrastructure/images_version** - Images Version metadata
4. **Infrastructure/images** - Docker images
5. **Infrastructure/configure** - Jenkins Configuration
6. **joara-app-provision** - Joara CLI

## Usage in Linux

```shell
> wget https://repo.continuum.io/miniconda/Miniconda3-latest-Linux-x86_64.sh
> chmod +x Miniconda3-latest-Linux-x86_64.sh
> ./Miniconda3-latest-Linux-x86_64.sh
> export PATH=/home/user/miniconda3/bin:$PATH
> conda create -n vjoaraapp3 python
> source activate vjoaraapp3
> git clone joara
> pip install --editable joara-app-provision
> joara -d dev bootstrap --group acs


```