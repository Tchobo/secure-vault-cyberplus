from rest_framework.throttling import UserRateThrottle


class UploadRateThrottle(UserRateThrottle):
    scope = 'upload'


class DownloadRateThrottle(UserRateThrottle):
    scope = 'download'
