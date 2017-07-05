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

WPS_SERVER = 'aims2.llnl.gov'

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

def dimension(request, prefix, crs=None):
    name = get_method_param(request, prefix + '-name')

    start = get_method_param(request, prefix + '-start')

    stop = get_method_param(request, prefix + '-stop')

    step = get_method_param(request, prefix + '-step')

    if name is not None:
        prefix = name

    if crs is not None:
        data = "\tcwt.Dimension('{}', '{}', '{}', '{}'".format(prefix, start, stop, crs)
    else:
        data = "\tcwt.Dimension('{}', {}, {}".format(prefix, start, stop)

    data += ", step={}),\n".format(step)

    return data

@csrf_exempt
def wps_process(request):
    buf = StringIO.StringIO()

    buf.write("import cwt\nimport time\n\n")

    buf.write("key = 'YOUR KEY'\n\n")

    buf.write("wps = cwt.WPS('http://{}/wps', api_key=key)\n\n".format(WPS_SERVER)) 

    variable = get_method_param(request, 'variable')

    files = get_method_param(request, 'files').split(',')

    buf.write("inputs = [\n")

    for f in files:
        if f.split('/')[17] == variable:
            buf.write("\tcwt.Variable('{}', '{}'),\n".format(f, variable))

    buf.write("]\n\n")

    domain_modified = get_method_param(request, 'domain_modified')

    if domain_modified:
        dimensions = get_method_param(request, 'dimensions').split('|')

        buf.write("domain = cwt.Domain([\n")

        buf.write(dimension(request, 'time', 'timestamps'))

        buf.write(dimension(request, 'lon'))

        buf.write(dimension(request, 'lat'))

        for dim in dimensions:
            buf.write(dimension(request, 'dim-' + dim))

        buf.write("])\n\n")

    regrid = get_method_param(request, 'regrid')

    if regrid == 'Gaussian':
        lats = get_method_param(request, 'gaussian-lats')

        buf.write("regrid = cwt.Gridder(grid='gaussian~{}')\n\n".format(lats))
    elif regrid == 'Uniform':
        lons = get_method_param(request, 'uniform-lons')

        lats = get_method_param(request, 'uniform-lats')

        buf.write("regrid = cwt.Gridder(grid='uniform~{}x{}')\n\n".format(lons, lats))

    process = get_method_param(request, 'process')

    _, process = process.split('.')

    filename = '{}.py'.format(process)

    buf.write("proc = wps.get_process('{}')\n\n".format(process))

    buf.write("wps.execute(proc, inputs=inputs")

    if domain_modified:
        buf.write(", domain=domain")

    if regrid != 'None':
        buf.write(", gridder=regrid")

    buf.write(")\n\n")

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
        context['time_freq'] = time_freq_map.get(time_freq, None)
    else:
        context['variables'] = ['None']

    return render(request, 'cog/wps/wps.html', context)
