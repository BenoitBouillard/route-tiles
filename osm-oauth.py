###
# Consumer Key: twmK5Xz70qgOv7S7b7z9mq3iSAMRQjCwYeZgOkPY
# Consumer Secret: vCBFIWy4qGPnx9jErR51diu2N2gHnPbo6rWnjnzG

# Request Token URL: https://www.openstreetmap.org/oauth/request_token
# Access Token URL: https://www.openstreetmap.org/oauth/access_token
# Authorise URL: https://www.openstreetmap.org/oauth/authorize

# Requesting the following permissions from the user:
# We support HMAC-SHA1 (recommended) and RSA-SHA1 signatures.    

CLIENT_KEY = "twmK5Xz70qgOv7S7b7z9mq3iSAMRQjCwYeZgOkPY"
CLIENT_SECRET = "vCBFIWy4qGPnx9jErR51diu2N2gHnPbo6rWnjnzG"

REQUES_TOKEN_URL = "https://www.openstreetmap.org/oauth/request_token"



# Using OAuth1Session
from requests_oauthlib import OAuth1Session

# Using OAuth1 auth helper
import requests
from requests_oauthlib import OAuth1

# Using OAuth1Session
oauth = OAuth1Session(CLIENT_KEY, client_secret=CLIENT_SECRET)
fetch_response = oauth.fetch_request_token(REQUES_TOKEN_URL)
print(fetch_response)
# {
    # "oauth_token": "Z6eEdO8MOmk394WozF5oKyuAv855l4Mlqo7hhlSLik",
    # "oauth_token_secret": "Kd75W4OQfb2oJTV0vzGzeXftVAwgMnEK9MumzYcM"
# }
# >>> resource_owner_key = fetch_response.get('oauth_token')
# >>> resource_owner_secret = fetch_response.get('oauth_token_secret')

# >>> # Using OAuth1 auth helper
# >>> oauth = OAuth1(client_key, client_secret=client_secret)
# >>> r = requests.post(url=request_token_url, auth=oauth)
# >>> r.content
# "oauth_token=Z6eEdO8MOmk394WozF5oKyuAv855l4Mlqo7hhlSLik&oauth_token_secret=Kd75W4OQfb2oJTV0vzGzeXftVAwgMnEK9MumzYcM"
# >>> from urlparse import parse_qs
# >>> credentials = parse_qs(r.content)
# >>> resource_owner_key = credentials.get('oauth_token')[0]
# >>> resource_owner_secret = credentials.get('oauth_token_secret')[0]