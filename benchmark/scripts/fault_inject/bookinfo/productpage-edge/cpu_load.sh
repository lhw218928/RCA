file_path='/home/cron/jupiter-hybrid/bookinfo/productpage-edge/cpu_load.yaml'

count=1

echo ${file_path}

for ((i=1;i<=5;i++))
do
	echo "cpu_load_$count"
	kubectl apply -f ${file_path} -n chaos-mesh
	echo "$(date +"%Y-%m-%d %T") start create."
	sleep 180
	echo "$(date +"%Y-%m-%d %T") start delete."
	kubectl delete -f ${file_path} -n chaos-mesh
	echo "$(date +"%Y-%m-%d %T") finish delete."
	echo -e "\n"
	sleep 720
	((count++))
done