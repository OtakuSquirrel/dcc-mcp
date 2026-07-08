"""Cloud tunnel — outbound WSS reverse tunnel so remote agents can reach
a home daemon that sits behind NAT with no public IP and no open ports.

Both the daemon and the cloud agent dial OUT to a relay; the relay pairs
them by ``daemon_id`` and pipes frames. See ``protocol`` for the wire
format, ``relay`` for the public server, ``client`` for the daemon side.
"""
