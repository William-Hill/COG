import json
import StringIO
import urllib, urllib2
from collections import Counter

from django import http
from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt

INVALID_CHARS = "[<>&#%{}\[\]\$]"

WPS_SERVER = 'aims2.llnl.gov'

def write_wps_script(buf, identifier, inputs, var_name):
    buf.write("import cwt\nimport time\n\n")

    buf.write("key='YOUR KEY'\n\n")

    buf.write("wps = cwt.WPS('https://{}/wps', api_key=key)\n\n".format(WPS_SERVER))

    buf.write("proc = wps.get_process('{}')\n\n".format(identifier))

    buf.write("inputs = [\n")

    for i in inputs:
        buf.write("\tcwt.Variable('{}', '{}'),\n".format(i, var_name))

    buf.write("]\n\n")

    buf.write("wps.execute(proc, inputs=inputs)\n\n")

    buf.write("while proc.processing:\n")

    buf.write("\tprint proc.status\n\n")

    buf.write("\ttime.sleep(1)\n\n")

    buf.write("print proc.output")

def get_method_param(request, key):
    if request.method == 'GET':
        return request.GET.get(key, None)
    else:
        return request.POST.get(key, None)

@csrf_exempt
def wps_process(request, process, dataset_id, index_node):
    params = [
        ('type', 'File'), 
        ('dataset_id', dataset_id),
        ('format', 'application/solr+json'), 
        ('offset', 0)
    ]

    query = get_method_param(request, 'query')

    if query is not None and len(query.strip()) > 0:
        for c in INVALID_CHARS:
            if c in query:
                return HttpResponseBadRequest(ERROR_MESSAGE_INVALID_TEXT, content_type="text/plain")

        params.append(('query', query))

    shard = get_method_param(request, 'shard')

    if shard is not None and len(shard.strip()) > 0:
        params.append(('shards', shard + '/solr'))
    else:
        params.append(('distrib', 'false'))

    url = 'http://'+index_node+'/esg-search/search?'+urllib.urlencode(params)

    fh = urllib2.urlopen(url)

    response = fh.read().decode('UTF-8')

    data = json.loads(response)

    docs = data['response']['docs']

    inputs = {}

    for d in docs:
        for u in d.get('url', []):
            url, mime, endpoint = u.split('|')

            if endpoint == 'OPENDAP':
                file_url = url.replace('.html', '')

                inputs[file_url] = d.get('variable')

    candidates = Counter([x for y in inputs.values() for x in y])

    candidate_keys = candidates.keys()

    var_name = None

    # match a query parameter as a variable name
    for arg in query:
        if arg in candidate_keys:
            var_name = arg

            break
    
    # choose most common name
    if var_name is None:
        try:
            var_name, _ = candidates.most_common()[0]
        except IndexError:
            return HttpResponseBadRequest('Unable to determine variable name.')

    output = StringIO.StringIO()

    write_wps_script(output, 'CDAT.aggregate', inputs, var_name)

    response = HttpResponse(output.getvalue(), content_type='text/x-script.phyton')

    response['Content-Length'] = output.tell()
    response['Content-Disposition'] = 'attachment; filename=aggregate.py'

    output.close()

    return response
