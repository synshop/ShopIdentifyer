#!/bin/bash
clear
echo Access logger started

tail -0f /home/access/scripts/access_log.txt | egrep --line-buffered -i "presented" | while read line
    do
        msg="`tail -7 /home/access/scripts/access_log.txt | grep presented`"
        tag="`echo $msg | awk '{ print $5 }'`"
	reader="`echo $msg | awk '{ print $10 }'`"
	user="`cat /home/access/scripts/users.txt | grep $tag | awk '{ print $4 }'`"
	echo ${tag};
	# curl -X -d tag=${tag} -d reader=${reader} https://<insert.ip.here>/swipe
    done
