from agavepy.agave import Agave, AgaveException
from designsafe.apps.licenses.models import LICENSE_TYPES
from designsafe.apps.notifications.views import get_number_unread_notifications
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpResponse
from django.shortcuts import render, redirect
from requests import HTTPError
import json
import logging


logger = logging.getLogger(__name__)

@login_required
def index(request):
    context = {}
    token_key = getattr(settings, 'AGAVE_TOKEN_SESSION_ID')
    if token_key in request.session:
        context['session'] = {
            'agave': json.dumps(request.session[token_key])
        }
    context['unreadNotifications'] = get_number_unread_notifications(request)
    if request.user.is_superuser:
        return render(request, 'designsafe/apps/applications/index.html', context)
    else:
        return render(request, 'designsafe/apps/applications/denied.html', context)


def _app_license_type(app_id):
    app_lic_type = app_id.split('-')[0].upper()
    lic_type = next((t[0] for t in LICENSE_TYPES if t[0] == app_lic_type), None)
    return lic_type

@login_required
def call_api(request, service):
    try:
        token = request.user.agave_oauth
        agave = Agave(api_server=settings.AGAVE_TENANT_BASEURL, token=token.access_token)
        if service == 'apps':
            appId = request.GET.get('appId')
            pems = request.GET.get('pems')
            # username = request.GET.get('username')

            if request.method == 'GET':
                if appId:
                    if pems:
                        data = agave.apps.listPermissions(appId=appId)
                    else:
                        data = agave.apps.get(appId=appId)
                        lic_type = _app_license_type(appId)
                        data['license'] = {
                            'type': lic_type
                        }
                        if lic_type is not None:
                            lic = request.user.licenses.filter(license_type=lic_type).first()
                            data['license']['enabled'] = lic is not None
            elif request.method == 'POST':
                body = json.loads(request.body)
                if (appId):
                    if pems:
                        username = request.GET.get('username')
                        data = agave.apps.updatePermissionsForUser(appId=appId, username=username, body=body)
                    else:
                        data = agave.apps.manage(appId=appId, body=body)
                else:
                    data = agave.apps.add(body=body)
            elif request.method == 'DELETE':
                if appId:
                    if pems:
                        username = request.GET.get('username')
                        data = agave.apps.deletePermissionsForUser(appId=appId, username=username)
                    else:
                        data = agave.apps.delete(appId=appId)

        elif service == 'files':
            system_id = request.GET.get('system_id')
            path = request.GET.get('path')
            if (system_id and path):
                data = agave.files.list(systemId=system_id, filePath=path)

        elif service == 'systems':
            system_id = request.GET.get('system_id')
            public = request.GET.get('public')
            type = request.GET.get('type')

            if request.method == 'GET':
                if system_id:
                    data = agave.systems.get(systemId=system_id)
                else:
                    if (public):
                        if (type):
                            data = agave.systems.list(public=public, type=type)
                        else:
                            data = agave.systems.list(public=public)
                    else:
                        if (type):
                            data = agave.systems.list(type=type)
                        else:
                            data = agave.systems.list()

        elif service == 'meta':
            uuid = request.GET.get('uuid')
            pems = request.GET.get('pems')
            query = request.GET.get('q')
            if request.method == 'GET':
                if pems:
                    if uuid:
                        data = agave.meta.listMetadataPermissions(uuid=uuid)
                else:
                    if uuid:
                        data = agave.meta.getMetadata(uuid=uuid)
                    elif query:
                        data = agave.meta.listMetadata(q=query)
                    else:
                        data = agave.meta.listMetadata()
            elif request.method == 'POST':
                body = json.loads(request.body)
                if pems:
                    username = request.GET.get('username')
                    if username:
                        data = agave.meta.updateMetadataPermissionsForUser(body=body, uuid=uuid, username=username)
                    else:
                        data = agave.meta.updateMetadata(body=body, uuid=uuid)
                else:
                    if uuid:
                        data = agave.meta.updateMetadata(uuid=uuid, body=body)
                    else:
                        data = agave.meta.addMetadata(body=body)

            elif request.method == 'DELETE':
                if uuid:
                    if pems:
                        username = request.GET.get('username')
                        data = agave.meta.deleteMetadataPermissionsForUser(uuid=uuid, username=username)
                    else:
                        data = agave.meta.deleteMetadata(uuid=uuid)

        else:
            return HttpResponse('Unexpected service: %s' % service, status=400)
    except AgaveException as e:
        logger.error('Failed to execute {0} API call due to AgaveException={1}'.format(
            service, e.message))
        return HttpResponse(json.dumps(e.message), content_type='application/json',
                            status=400)
    except HTTPError as e:
        try:
            json_response = e.response.json()
            logger.error('Failed to execute {0} API call due to HTTPError={1}'.format(
            service, json_response.get('message')))
            return HttpResponse(json.dumps(json_response.get('message')),
                    content_type='application/json',
                    status=400)
        except Exception as e:
            return HttpResponse(json.dumps(e.message),
                    content_type='application/json',
                    status=400)

    except Exception as e:
        logger.error('Failed to execute {0} API call due to Exception={1}'.format(
            service, e.message))
        return HttpResponse(
            json.dumps({'status': 'error', 'message': '{}'.format(e.message)}),
            content_type='application/json', status=400)

    return HttpResponse(json.dumps(data, cls=DjangoJSONEncoder),
                        content_type='application/json')
