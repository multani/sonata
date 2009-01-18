#!/bin/bash

prev_version=1.5.3
version=1.6

cd $(dirname "$0")
cd ..

# Update version numbers

sed -i 's/'"$prev_version"'/'"$version"'/' setup.py
sed -i 's/'"$prev_version"'/'"$version"'/' sonata/consts.py

# Create archive, removing:
#   - website directory
#   - .svn directories
#   - .pyc files

cd ..
cp -R trunk/ sonata-$version
find sonata-$version/ -name .svn -exec rm -rf {} \; &> /dev/null
find sonata-$version/ -name *.pyc -exec rm -f {} \;
rm -rf sonata-$version/website/

tar zcvf sonata-$version.tar.gz sonata-$version
tar jcf sonata-$version.tar.bz2 sonata-$version

rm -rf sonata-$version/
