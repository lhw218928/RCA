file_path='/home/cron/jupiter-hybrid/bookinfo/reviews-v3-edge/net_latency.yaml'

echo ${file_path}

let count=1

for ((i=1;i<=2;i++))
do
	echo net_latency_$count
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