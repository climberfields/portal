from __future__ import absolute_import

from celery import shared_task, task
from designsafe.celery import app

from agavepy.agave import Agave, AgaveException

import logging
import requests
import json

from django.http import HttpResponse
logger = logging.getLogger(__name__)

@app.task
def submit_job(agave, job_post):
# def submit_job(server, access_token, job_post): #doing it this way returns AsyncResult but all the methods cause a decode error
# agave = Agave(api_server=server, token=access_token)
    logger.info('submitting job: {0}'.format(job_post))
    try:
      response=agave.jobs.submit(body=job_post)
    except (requests.exceptions.ConnectionError, requests.exceptions.HTTPError) as e:
        logger.info('Task HTTPError: {}'.format(e.__class__))
        submit_job.retry(exc=e("Agave is currently down. Your job will be submitted when it returns."), max_retries=None)
    logger.info('agave response: {}'.format(response))

    # mock_agave_notification(response)
    mock_agave_notification() #for testing

    d = {
        "url" : "http://requestb.in/w59adew5",
        # "url" : "http://designsafe-ci.org/webhooks/job?uuid={UUID}&status=${EVENT}&ob_id=${JOB_ID}&event=${EVENT}&system=${JOB_SYSTEM}&job_name=${JOB_NAME}&job_owner=${JOB_OWNER}",
        "event" : "*",
        "associatedUuid" : str(response.id),
        "persistent": True
    }
    subscribe = agave.notifications.add(body=json.dumps(d))
    logger.info('agave subs: {}'.format(subscribe))

    return response

#just for testing
# def mock_agave_notification(response):
def mock_agave_notification():
    import requests
    # r = requests.post('http://requestb.in/w59adew5', data={"job_id":response.id, "event":"JOB_CREATED", "job_name":response.name})
    r = requests.post('http://192.168.99.100:8000/webhooks/jobs/', data={"job_id":'1234512345', "event":"test", "job_name":'test name', "job_owner": 'mlm55'})
