#!/bin/bash
clear
echo Access logger started

tail -0f /home/access/scripts/access_log.txt | egrep --line-buffered -i "granted" | while read line
    do
		msg="`tail -7 /home/access/scripts/access_log.txt | grep granted`"
		tag="`echo $msg | awk '{ print $5 }'`"
		reader="`echo $msg | awk '{ print $10 }'`"
		# echo ${tag};
		curl -X -d tag=${tag} -d reader=${reader} https://<insert.ip.here>/swipe
    done
