"""
Client wrapper for Amazon's Simple Storage Service.

API stability: unstable.

Various API-incompatible changes are planned in order to expose missing
functionality in this wrapper.
"""


from hashlib import md5
from base64 import b64encode


from epsilon.extime import Time

from twisted.web.client import getPage
from twisted.web.http import datetimeToString

from txaws.credentials import AWSCredentials
from txaws.util import XML


def calculateMD5(data):
    digest = md5(data).digest()
    return b64encode(digest)


class S3Request(object):
    def __init__(self, verb, bucket=None, objectName=None, data='',
            contentType=None, metadata={}, rootURI='https://s3.amazonaws.com',
            creds=None):
        self.verb = verb
        self.bucket = bucket
        self.objectName = objectName
        self.data = data
        self.contentType = contentType
        self.metadata = metadata
        self.rootURI = rootURI
        self.creds = creds
        self.date = datetimeToString()

    def getURIPath(self):
        path = '/'
        if self.bucket is not None:
            path += self.bucket
            if self.objectName is not None:
                path += '/' + self.objectName
        return path

    def getURI(self):
        return self.rootURI + self.getURIPath()

    def getHeaders(self):
        headers = {'Content-Length': len(self.data),
                   'Content-MD5': calculateMD5(self.data),
                   'Date': self.date}

        for key, value in self.metadata.iteritems():
            headers['x-amz-meta-' + key] = value

        if self.contentType is not None:
            headers['Content-Type'] = self.contentType

        if self.creds is not None:
            signature = self.getSignature(headers)
            headers['Authorization'] = 'AWS %s:%s' % (self.creds.access_key, signature)

        return headers

    def getCanonicalizedResource(self):
        return self.getURIPath()

    def getCanonicalizedAmzHeaders(self, headers):
        result = ''
        headers = [(name.lower(), value) for name, value in headers.iteritems() if name.lower().startswith('x-amz-')]
        headers.sort()
        return ''.join('%s:%s\n' % (name, value) for name, value in headers)

    def getSignature(self, headers):
        text = self.verb + '\n'
        text += headers.get('Content-MD5', '') + '\n'
        text += headers.get('Content-Type', '') + '\n'
        text += headers.get('Date', '') + '\n'
        text += self.getCanonicalizedAmzHeaders(headers)
        text += self.getCanonicalizedResource()
        return self.creds.sign(text)

    def submit(self):
        return self.getPage(url=self.getURI(), method=self.verb, postdata=self.data, headers=self.getHeaders())

    def getPage(self, *a, **kw):
        return getPage(*a, **kw)


NS = '{http://s3.amazonaws.com/doc/2006-03-01/}'

class S3(object):
    rootURI = 'https://s3.amazonaws.com/'
    requestFactory = S3Request

    def __init__(self, creds):
        self.creds = creds

    def makeRequest(self, *a, **kw):
        """
        Create a request with the arguments passed in.

        This uses the requestFactory attribute, adding the credentials to the
        arguments passed in.
        """
        return self.requestFactory(creds=self.creds, *a, **kw)

    def _parseBucketList(self, response):
        """
        Parse XML bucket list response.
        """
        root = XML(response)
        for bucket in root.find(NS + 'Buckets'):
            yield {'name': bucket.findtext(NS + 'Name'),
                   'created': Time.fromISO8601TimeAndDate(bucket.findtext(NS + 'CreationDate'))}

    def listBuckets(self):
        """
        List all buckets.

        Returns a list of all the buckets owned by the authenticated sender of
        the request.
        """
        return self.makeRequest('GET').submit().addCallback(self._parseBucketList)

    def createBucket(self, bucket):
        """
        Create a new bucket.
        """
        return self.makeRequest('PUT', bucket).submit()

    def deleteBucket(self, bucket):
        """
        Delete a bucket.

        The bucket must be empty before it can be deleted.
        """
        return self.makeRequest('DELETE', bucket).submit()

    def putObject(self, bucket, objectName, data, contentType=None, metadata={}):
        """
        Put an object in a bucket.

        Any existing object of the same name will be replaced.
        """
        return self.makeRequest('PUT', bucket, objectName, data, contentType, metadata).submit()

    def getObject(self, bucket, objectName):
        """
        Get an object from a bucket.
        """
        return self.makeRequest('GET', bucket, objectName).submit()

    def headObject(self, bucket, objectName):
        """
        Retrieve object metadata only.

        This is like getObject, but the object's content is not retrieved.
        Currently the metadata is not returned to the caller either, so this
        method is mostly useless, and only provided for completeness.
        """
        return self.makeRequest('HEAD', bucket, objectName).submit()

    def deleteObject(self, bucket, objectName):
        """
        Delete an object from a bucket.

        Once deleted, there is no method to restore or undelete an object.
        """
        return self.makeRequest('DELETE', bucket, objectName).submit()
