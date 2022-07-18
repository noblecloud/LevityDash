# WeatherFlow/Tempest

The current implementation only supports one station and has no GUI for configuring it.

### Access Token:

You can find or generate your access token here: https://tempestwx.com/settings/tokens

### StationID and DeviceID

1. Open to your station list here: https://tempestwx.com/settings/stations
2. Click or tap the station you want to use
3. Click or tap 'Status'

From there you can find both the station ID and the device ID.

> [!NOTE]
> Since only one device ID is supported, I imagine using data from both Air and Sky is not possible. Thankfully, the device ID is only used for getting historical data.

### Example

```ini

[Config] ; Since the config file is an INI, a main section must be provided
enabled = False

; Enables/disables socket updates
socketUpdates = True

; Set socket to web or udp
socketType = web

; Enables/disables getting historical when the plugin is loaded.
fetchHistory = False

;This is the ID of the station you want to monitor
stationID = {StationID}

;Only used for getting historical data
deviceID = {DeviceID}

;https://tempestwx.com/settings/tokens
token = {API Token}

;Defines that this plugin should take priority as the data source
defaultFor = temperature wind ... 
```