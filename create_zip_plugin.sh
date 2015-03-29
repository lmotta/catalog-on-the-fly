#!/bin/bash
plugin_dir=$( basename $( pwd ) )
if [ ! -f $plugin_dir".zip" ]; then
  rm $plugin_dir".zip"
fi
mkdir $plugin_dir
cp *.py $plugin_dir
for item in "catalogotf.svg resources_rc.qrc metadata.txt README.md LICENSE"; do cp $item $plugin_dir; done
zip -r $plugin_dir $plugin_dir
rm -r $plugin_dir
