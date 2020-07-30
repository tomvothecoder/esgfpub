#!/bin/bash

utcStart=`date +%s`

tag="BGC_CTC_raw - DB Ingest-Only"
mapfile_dir=/p/user_pub/e3sm/staging/mapfiles/mapfiles_bgc_raw
mapfile_done=/p/user_pub/e3sm/staging/mapfiles/mapfiles_archive/BGC/mapfiles_bgc_raw
project=e3sm
email_recip=bartoletti1@llnl.gov

ini_dir=/p/user_pub/e3sm/staging/ini_std

mapfiles=( `ls $mapfile_dir` )
mapfile_count=${#mapfiles[@]}

ts=`date +%Y%m%d.%H%M%S`
echo "$ts: INPROCESS: mapfile ingestion to database ($mapfile_count mapfiles)"
for mapfile in "${mapfiles[@]}"
do
    esgpublish -i $ini_dir --project $project --map $mapfile_dir/$mapfile --commit-every 100  --no-thredds-reinit
    if [ $? != 0 ] ; then
        echo Failed to engest $mapfile into the database
        exit 1
    fi
    echo Successfully engested $mapfile into the database
done
ts=`date +%Y%m%d.%H%M%S`
echo "$ts: COMPLETED: mapfile ingestion to database ($mapfile_count mapfiles)"

utcFinal=`date +%s`
elapsed=$(($utcFinal - $utcStart))

echo "All done ($tag).  Elapsed time:  $elapsed seconds" | sendmail $email_recip

