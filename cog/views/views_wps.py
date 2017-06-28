import datetime
import json
import re
import StringIO
import urllib, urllib2
from collections import Counter

from django import http
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt

INVALID_CHARS = "[<>&#%{}\[\]\$]"

WPS_SERVER = '10.5.5.5:8001'

def get_method_param(request, key):
    if request.method == 'GET':
        return request.GET.get(key, None)
    else:
        return request.POST.get(key, None)

def retrieve_files(request):
    dataset_id = get_method_param(request, 'dataset_id')

    index_node = get_method_param(request, 'index_node')

    shard = get_method_param(request, 'shard')

    query = get_method_param(request, 'query')

    params = [
        ('type', 'File'), 
        ('dataset_id', dataset_id),
        ('format', 'application/solr+json'), 
        ('offset', 0)
    ]

    if query is not None and len(query.strip()) > 0:
        for c in INVALID_CHARS:
            if c in query:
                return HttpResponseBadRequest(ERROR_MESSAGE_INVALID_TEXT, content_type="text/plain")

        params.append(('query', query))

    if shard is not None and len(shard.strip()) > 0:
        params.append(('shards', shard + '/solr'))
    else:
        params.append(('distrib', 'false'))

    url = 'http://'+index_node+'/esg-search/search?'+urllib.urlencode(params)

    response = urllib2.urlopen(url)

    return response.read().decode('UTF-8')

def find_access_url(urls, access_type):
    for candidate in urls:
        url, mime, atype = candidate.split('|')

        if atype == access_type:
            return url

    return None

time_formats = {
    'day': '%Y%m%d',
    'mon': '%Y%m',
    'yr': '%Y'
}

time_freq_map = {
    'day': 'Day',
    'mon': 'Month',
    'yr': 'Year',
}

@csrf_exempt
def wps_process(request):
    data = ''
    filename = 'test.py'

    buf = StringIO.StringIO()

    buf.write("import cwt\nimport time\n\n")

    buf.write("key = 'YOUR KEY'\n\n")

    buf.write("wps = cwt.WPS('http://{}/wps', api_key=key)\n\n".format(WPS_SERVER)) 

    variable = get_method_param(request, 'variable')

    files = get_method_param(request, 'files').split(',')

    buf.write("inputs = [\n")

    for f in files:
        buf.write("\tcwt.Variable('{}', '{}'),\n".format(f, variable))

    buf.write("]\n\n")

    domain_modified = get_method_param(request, 'domain_modified')

    if domain_modified:
        lon_start = get_method_param(request, 'lon-start')

        lon_stop = get_method_param(request, 'lon-stop')

        lon_step = get_method_param(request, 'lon-step')

        lat_start = get_method_param(request, 'lat-start')

        lat_stop = get_method_param(request, 'lat-stop')

        lat_step = get_method_param(request, 'lat-step')

        time_start = get_method_param(request, 'time-start')

        time_stop = get_method_param(request, 'time-stop')

        time_step = get_method_param(request, 'time-step')

        buf.write("domain = cwt.Domain([\n")

        buf.write("\tcwt.Dimension('time', '{}', '{}', 'timestamps', step={}),\n".format(time_start, time_stop, time_step))

        buf.write("\tcwt.Dimension('longitude', {}, {}, step={}),\n".format(lon_start, lon_stop, lon_step))

        buf.write("\tcwt.Dimension('latitude', {}, {}, step={}),\n".format(lat_start, lat_stop, lat_step))

        buf.write("])\n\n")

    process = get_method_param(request, 'process')

    buf.write("proc = wps.get_process('{}')\n\n".format(process))

    if domain_modified:
        buf.write("wps.execute(proc, inputs=inputs, domain=domain)\n\n")
    else:
        buf.write("wps.execute(proc, inputs=inputs)\n\n")

    buf.write("while proc.processing:\n")

    buf.write("\tprint proc.status\n\n")

    buf.write("\ttime.sleep(1)\n\n")

    buf.write("print proc.status")

    response = HttpResponse(buf.getvalue(), content_type='text/x-script.phyton')

    response['Content-Disposition'] = 'attachment; filename={}'.format(filename)

    return response

@csrf_exempt
def wps(request):
    context = {}

    try:
        files = retrieve_files(request) 
    except Exception:
        files = None

    if files is not None:
        data = json.loads(files)

        docs = data['response']['docs']

        var_names = [x for d in docs for x in d.get('variable', [])]

        files = [find_access_url(x.get('url', []), 'OPENDAP') for x in docs]

        files = [x.replace('.html', '') if x is not None else None for x in files]

        pattern = re.compile('.*/.*_(\d+)-(\d+)\.nc')

        time_freq = docs[0]['time_frequency'][0]

        times = sorted([x for y in files for x in pattern.match(y).groups()])

        start = datetime.datetime.strptime(times[0], time_formats.get(time_freq))

        stop = datetime.datetime.strptime(times[-1], time_formats.get(time_freq))

        context['variables'] = list(set(var_names))
        context['wps_server'] = WPS_SERVER
        context['files'] = files
        context['time'] = [start, stop]
        context['time_freq'] = time_freq_map.get(time_freq, 'Unknown')
    else:
        context['variables'] = ['None']

    return render(request, 'cog/wps/wps.html', context)
