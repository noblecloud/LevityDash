AMBIENT_ENDPOINT='https://api.ambientweather.net/v1'
AMBIENT_API_KEY='e574e1bfb9804a52a1084c9f1a4ee5d88e9e850fc1004aeaa5010f15c4a23260'
AMBIENT_APPLICATION_KEY='ec02a6c4e29d42e086d98f5db18972ba9b93d864471443919bb2956f73363395'

from ambient_api.ambientapi import AmbientAPI
import time

api = AmbientAPI(AMBIENT_ENDPOINT='https://api.ambientweather.net/v1',
				 AMBIENT_API_KEY='e574e1bfb9804a52a1084c9f1a4ee5d88e9e850fc1004aeaa5010f15c4a23260',
				 AMBIENT_APPLICATION_KEY='ec02a6c4e29d42e086d98f5db18972ba9b93d864471443919bb2956f73363395')

devices = api.get_devices()

device = devices[0]

time.sleep(1) #pause for a second to avoid API limits

print(device.get_data()[0])
