# pool-ari

This is a proxy server specific to the API of the Ariston water heater appliances. It supports
configuring a pool of credentials and they are used in round robin manner to relay the requests
coming from the clients (e.g. the [Python Ariston package](https://pypi.org/project/ariston/).
With the help of multiple accounts, you may [decrease the polling interval](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/issues/332)
to an acceptable level (e.g. every 60 seconds).

## Setup

1. Register additional accounts (for your family members of course) at http://www.ariston-net.remotethermo.com/

2. Using the official mobile application, share all devices with them (so they will be the guest accounts).
All these guest accounts are supposed to see the exact same set of equipments.

3. Setup this proxy server. By default, it is listening on port 9999, no TLS. You need to configure the following environment variables:

- `AUTH_USR`/`AUTH_PWD`: the username/password for accessing the proxy (it is **not** used to talk to the official upstream)
- `POOL_[n]_USR`/`POOL_[n]_PWD` a pool of guest account credentials, where `[n]` starts from zero. E.g. `POOL_0_USR`.
You must configure at least one CRED, but obviously it doesn't help if you have only a single account.

You can either:
- use the docker image from ghcr.io
- just place this script to your config dir inside HA, then use [shell_command](https://www.home-assistant.io/integrations/shell_command/) 
integration along with [Home Assistant trigger platform](https://www.home-assistant.io/docs/automation/trigger/#home-assistant-trigger)
- host it somewhere else as you prefer

4. Reconfigure your client (e.g. the [HA integration](https://github.com/fustom/ariston-remotethermo-home-assistant-v3))
to target the proxy, e.g. `http://1.2.3.4:9999/api/v2/`.
