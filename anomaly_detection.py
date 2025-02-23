import numpy as np
from sklearn.cluster import Birch
from sklearn import preprocessing
from sklearn.metrics.pairwise import pairwise_distances
import pandas as pd
from util.utils import df_time_limit_normalization, df_time_limit, normalize_series, time_string_2_timestamp


def get_anomaly_by_df(config, base_dir, file_dir, label, begin_timestamp, end_timestamp):
    anomalies = []
    anomaly_time_series = {}
    # read call latency data
    call_data = pd.read_csv(file_dir + '/' + 'call.csv')
    anomaly_svc_calls, anomaly_call_time_series_index = anomaly_detection_with_smoothing(
        df_time_limit(call_data, begin_timestamp, end_timestamp), masks=['p50', 'p99'], threshold=config.anomaly_threshold)
    anomaly_time_series_index_combine = {}
    for node in anomaly_call_time_series_index:
        callee = node[:node.rfind('&')].split('_')[1]
        node_index = anomaly_time_series_index_combine.get(callee, [])
        node_index.extend(anomaly_call_time_series_index[node])
        anomaly_time_series_index_combine[callee] = node_index
    anomaly_time_series = {**anomaly_time_series, **anomaly_time_series_index_combine}
    a_svc_calls = [a[:a.rfind('&')].split('_')[1] for a in anomaly_svc_calls]
    anomalies.extend(a_svc_calls)
    # read svc latency data
    latency_data = pd.read_csv(file_dir + '/' + 'latency.csv')
    anomaly_svcs, anomaly_latency_time_series_index = anomaly_detection_with_smoothing(
        df_time_limit(latency_data, begin_timestamp, end_timestamp), masks=['p50', 'p99'], threshold=config.anomaly_threshold)
    for latency_node in anomaly_latency_time_series_index:
        node = latency_node[:latency_node.rfind('&')]
        node_index = anomaly_time_series_index_combine.get(node, [])
        node_index.extend(anomaly_latency_time_series_index[latency_node])
        anomaly_time_series_index_combine[node] = node_index
    anomaly_time_series = {**anomaly_time_series, **anomaly_time_series_index_combine}
    anomalies.extend([a_svc[:a_svc.rfind('&')] for a_svc in anomaly_svcs])
    # qps data
    qps_file_name = file_dir + '/' + 'svc_qps.csv'
    qps_source_data = pd.read_csv(qps_file_name)
    anomaly_qps, anomaly_qps_time_series_index = anomaly_detection_with_smoothing(
        df_time_limit(qps_source_data, begin_timestamp, end_timestamp), threshold=config.anomaly_threshold)
    for node in anomaly_qps_time_series_index:
        node_index = anomaly_time_series_index_combine.get(node, [])
        node_index.extend(anomaly_qps_time_series_index[node])
        anomaly_time_series_index_combine[node] = node_index
    anomaly_time_series = {**anomaly_time_series, **anomaly_time_series_index_combine}
    anomalies.extend([a_svc for a_svc in anomaly_qps])
    # success rate data
    success_rate_file_name = file_dir + '/' + 'success_rate.csv'
    success_rate_source_data = pd.read_csv(success_rate_file_name)
    anomaly_success_rate, anomaly_success_rate_time_series_index = anomaly_detection_with_smoothing(
        df_time_limit(success_rate_source_data, begin_timestamp, end_timestamp), threshold=config.anomaly_threshold)
    for node in anomaly_success_rate_time_series_index:
        node_index = anomaly_time_series_index_combine.get(node, [])
        node_index.extend(anomaly_success_rate_time_series_index[node])
        anomaly_time_series_index_combine[node] = node_index
    anomaly_time_series = {**anomaly_time_series, **anomaly_time_series_index_combine}
    anomalies.extend([a_svc for a_svc in anomaly_success_rate])
    # instances data
    instance_file_name = file_dir + '/' + 'instance.csv'
    instance_source_data = pd.read_csv(instance_file_name)
    anomalies_index = df_time_limit_normalization_ctn_anomalies_with_index(instance_source_data, begin_timestamp,
                                                                           end_timestamp, threshold=config.anomaly_threshold)
    anomalies.extend([a_instance[:a_instance.rfind('_')] for a_instance in anomalies_index.keys()])
    anomalies = list(set(anomalies))
    if 'istio-ingressgateway' in anomalies:
        anomalies.remove('istio-ingressgateway')
    for a_instance in anomalies_index:
        a_i = anomaly_time_series_index_combine.get(a_instance[:a_instance.rfind('_')], [])
        a_i.extend(anomalies_index[a_instance])
        anomaly_time_series_index_combine[a_instance[:a_instance.rfind('_')]] = a_i
    anomaly_time_series = {**anomaly_time_series, **anomaly_time_series_index_combine}
    record_anomalies(anomalies, anomalies_index, base_dir, label)
    return anomalies, anomaly_time_series


def anomaly_detection_with_smoothing(df, masks=None, threshold=0.03, smoothing_window=6, n=6):
    # anomaly detection on response time of service invocation.
    # input: response times of service invocations, threshold for birch clustering
    # output: anomalous service invocation
    if masks is None:
        masks = []
    df_time_index, df_index_time = get_timestamp_index(df)
    anomalies = []
    anomaly_time_series_index = {}
    for node, metrics in df.iteritems():
        # No anomaly detection in db
        if node != 'timestamp' and 'Unnamed' not in node and 'node' not in node and 'tcp' not in node:
            is_mask = False
            for mask in masks:
                if mask in node:
                    is_mask = True
            if is_mask:
                continue
            metrics = normalize_series(metrics)
            metrics = metrics.rolling(
                window=smoothing_window, min_periods=1).mean()
            x = np.array(metrics)
            x = np.where(np.isnan(x), -1, x)
            X = x.reshape(-1, 1)
            brc = Birch(branching_factor=50, n_clusters=None,
                        threshold=threshold, compute_labels=True)
            brc.fit(X)
            brc.predict(X)
            labels = brc.labels_
            n_clusters = np.unique(labels).size
            if n_clusters > 1:
                mean_vector = np.mean(X, axis=0)
                distances_to_cluster_centers = pairwise_distances(X, [mean_vector]).flatten()
                n_outlying_indices = np.argsort(distances_to_cluster_centers)[-n:]
                if len(n_outlying_indices) > 0:
                    anomalies.append(node)
                    anomaly_time_series_index[node] = [df_index_time[item] for item in n_outlying_indices.tolist()]
    return anomalies, anomaly_time_series_index


def anomaly_detection_with_smoothing_series(series, threshold=0.03, smoothing_window=6, n=6):
    anomaly_time_series_index = []
    metrics = normalize_series(series)
    metrics = metrics.rolling(
        window=smoothing_window, min_periods=1).mean()
    x = np.array(metrics)
    x = np.where(np.isnan(x), -1, x)
    X = x.reshape(-1, 1)
    brc = Birch(branching_factor=50, n_clusters=None,
                threshold=threshold, compute_labels=True)
    brc.fit(X)
    brc.predict(X)
    labels = brc.labels_
    n_clusters = np.unique(labels).size
    is_anomaly = False
    if n_clusters > 1:
        mean_vector = np.mean(X, axis=0)
        distances_to_cluster_centers = pairwise_distances(X, [mean_vector]).flatten()
        n_outlying_indices = np.argsort(distances_to_cluster_centers)[-n:]
        if len(n_outlying_indices) > 0:
            is_anomaly = True
            anomaly_time_series_index.extend(n_outlying_indices)
    return is_anomaly, list(set(anomaly_time_series_index))


def df_time_limit_normalization_ctn_anomalies_with_index(df, begin_timestamp, end_timestamp, threshold):
    df = df_time_limit(df, begin_timestamp, end_timestamp)
    df_time_index, df_index_time = get_timestamp_index(df)
    anomalies_index = {}
    for node, metrics in df.iteritems():
        if not node == 'timestamp':
            series_list = []
            boundary_index = (metrics != -1)
            if_exist = False
            index = []
            for i, a in enumerate(boundary_index):
                if not if_exist and a:
                    if_exist = True
                    index.append(i)
                elif if_exist and not a:
                    if_exist = False
                    index.append(i - 1)
            if if_exist:
                index.append(len(boundary_index) - 1)
            if len(index) == 2 and index[0] == 0 and index[1] == len(boundary_index) - 1:
                prune_series = metrics
            else:
                for i in range(0, len(index) - 1, 2):
                    series_list.append(metrics[index[i]:index[i + 1] + 1])
                prune_series = pd.concat(series_list, axis=0)
            is_anomaly, anomaly_time_series_index = anomaly_detection_with_smoothing_series(prune_series, threshold=threshold)
            if is_anomaly:
                anomalies_index[node] = [df_index_time[idx + index[0]] for idx in anomaly_time_series_index]
    return anomalies_index


def get_timestamp_index(df):
    df_time_index = {}
    df_index_time = {}
    for node, metrics in df.iteritems():
        if node == 'timestamp':
            for t_index, t in enumerate(metrics):
                df_time_index[t] = t_index
                df_index_time[t_index] = t
            break
    return df_time_index, df_index_time


def record_anomalies(anomalies, anomalies_index, dir, label):
    with open(dir + '/result-anomaly_detection-' + label + '.log', "a") as output_file:
        print(anomalies, file=output_file)
        print(anomalies_index, file=output_file)
