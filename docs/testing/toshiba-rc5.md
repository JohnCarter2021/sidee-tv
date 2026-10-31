# Toshiba connection test build

This describes the changes released in Sidee 0.1.4.2. Toshiba Z670 compatibility
has not been confirmed on hardware.

It tries static authentication first on a fresh pairing, uses a separate short
MQTT connection identifier for static mode, and disables automatic connection
retries. Credentials use the brand declared by the TV, and the brand is saved
for reconnection. Existing paired topic identities and working profiles are preserved.
Every successful pairing still requires the TV PIN. A refusal now includes
the TV's advertised manufacturer, model, brand and transport protocol when
available, without copying MAC addresses, serial numbers or saved credentials.

1. Close the previous Sidee launcher. Extract this ZIP into a new folder.
2. Restart the TV once to begin this trial with a fresh connection service.
3. Open `start-windows.bat`, find the TV, and request its code once.
4. If it fails, copy the complete error, including the TV details at the end.
   Also report both TV models and firmware versions, whether the official
   VIDAA app still controls them after the failure, and whether that app is
   running on Android or iPhone.
5. If pairing succeeds, try installing one app and reconnecting after closing
   Sidee. Pairing success alone does not confirm tile installation support.

The static identifier separation follows
[pyvidaa's client implementation](https://github.com/warrenrees/pyvidaa/blob/master/pyvidaa/client.py).
Static-first ordering follows
[vidaa-control's Toshiba fallback](https://github.com/Lucent-/vidaa-control/blob/main/vidaa/client.py).
These changes need a trial on the affected TVs; they do not establish the cause
of the reported rejection.
