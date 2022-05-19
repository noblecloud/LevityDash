# WeatherFlow/Tempest

The current implementation only supports one station and has no GUI for configuring it.

```yaml
[Config]
enabled = False
socketUpdates = True
fetchHistory = False
stationID = {StationID}
deviceID = {DeviceID}
token = {API Token}
defaultFor = temperature wind pressure humidity light lightning
```