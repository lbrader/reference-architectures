# JOARA


## Code Details

1. **Infrastructure** - Provisiong of Infrastructure ARM templates, configuring jenkins and docker images
2. **Infrastructure/provisioning** - Provisioning Azure resources
3. **Infrastructure/images_version** - Images Version metadata
4. **Infrastructure/images** - Docker images
5. **Infrastructure/configure** - Jenkins Configuration
6. **joara-app-provision** - Joara CLI



## Usage in Linux

### Config

Azure credentials and others details can be configured in _cluster.ini_ file


```shell
> wget https://repo.continuum.io/miniconda/Miniconda3-latest-Linux-x86_64.sh
> chmod +x Miniconda3-latest-Linux-x86_64.sh
> ./Miniconda3-latest-Linux-x86_64.sh
> export PATH=/home/user/miniconda3/bin:$PATH
> conda create -n vjoaraapp3 python
> source activate vjoaraapp3
> git clone https://github.com/Snap-Analytx/joara-main.git
> cd joara-main
> pip install --editable joara-app-provision
> joara -d dev bootstrap --group all --verbose
> joara -d test bootstrap --group all –-verbose
> joara -d prod bootstrap --group all --verbose
> joara -d jenkins bootstrap --group jenkins --verbose
```

## To Destroy existing resources

```shell
joara -d prod destroy --group acs --verbose
joara -d dev destroy --group acs --verbose
joara -d test destroy --group acs --verbose
joara -d jenkins destroy --group jenkins --verbose
```