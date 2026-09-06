import unittest

from router_adapters import (
    FritzAdapter,
    latest_numeric_series_value,
    numeric_series,
)


class FakeFritzConnection:
    def __init__(self, access_type="Ethernet", common_utilization=True):
        self.access_type = access_type
        self.common_utilization = common_utilization
        self.services = [
            "DeviceInfo1",
            "WANPPPConnection1",
            "WANCommonInterfaceConfig1",
            "X_AVM-DE_WANFiber1",
        ]
        self.calls = []

    def call_action(self, service, action, **kwargs):
        self.calls.append((service, action, kwargs))
        if service == "WANPPPConnection1" and action == "GetInfo":
            return {
                "NewEnable": True,
                "NewName": "Internet",
                "NewConnectionStatus": "Connected",
                "NewUptime": 300,
                "NewExternalIPAddress": "100.64.0.10",
                "NewLastConnectionError": "ERROR_NONE",
                "NewTransportType": "PPPoE",
                "NewPPPoEACName": "test-pop",
            }
        if service == "DeviceInfo1" and action == "GetInfo":
            return {
                "NewUpTime": 400,
                "NewModelName": "Test FRITZ!Box",
                "NewSoftwareVersion": "8.20",
            }
        if service == "DeviceInfo1" and action == "GetDeviceLog":
            return {"NewDeviceLog": "log"}
        if service == "WANCommonInterfaceConfig1" and action == "GetCommonLinkProperties":
            result = {
                "NewWANAccessType": self.access_type,
                "NewPhysicalLinkStatus": "Up",
                # These are maxima of the utilization lists and must not be
                # exposed as the current WAN activity sample.
                "NewX_AVM-DE_DownstreamCurrentMaxSpeed": 999999,
                "NewX_AVM-DE_UpstreamCurrentMaxSpeed": 888888,
            }
            if self.common_utilization:
                result.update(
                    {
                        "NewX_AVM-DE_DownstreamCurrentUtilization": "100,200,321",
                        "NewX_AVM-DE_UpstreamCurrentUtilization": "10,20,45",
                    }
                )
            return result
        if service == "WANCommonInterfaceConfig1" and action == "X_AVM-DE_GetOnlineMonitor":
            return {
                "NewSyncGroupName": "sync_ata",
                "NewSyncGroupMode": "ATA",
                "Newds_current_bps": "100,200,300",
                "Newmc_current_bps": "900,900,900",
                "Newus_current_bps": "10,20,30",
            }
        if service == "X_AVM-DE_WANFiber1" and action == "GetInfo":
            return {
                "NewOpticalSignalLevel": -18250,
                "NewLowerOpticalThreshold": -28000,
                "NewUpperOpticalThreshold": -8000,
                "NewTransmitOpticalLevel": 2150,
                "NewLowerTransmitPowerThreshold": 1000,
                "NewUpperTransmitPowerThreshold": 5000,
                "NewSFPSerialNumber": "must-not-be-persisted",
                "NewFiberMode": "GPON",
            }
        if service == "X_AVM-DE_WANFiber1" and action == "GetStatistics":
            return {
                "NewResyncs": 2,
                "NewPacketErrorsReceived": 3,
                "NewPacketErrorsSent": 4,
            }
        raise RuntimeError(f"unsupported {service}.{action}")

    def get_cpu_temperatures(self):
        return [107]


class RouterAdapterTests(unittest.TestCase):
    def factory(self, fc):
        return lambda **_: fc

    def test_numeric_series_ignores_invalid_values(self):
        self.assertEqual(numeric_series("1,2,bad,3"), [1.0, 2.0, 3.0])
        self.assertEqual(numeric_series(None), [])

    def test_latest_numeric_series_value_uses_last_sample(self):
        self.assertEqual(latest_numeric_series_value("1,2,3"), 3.0)
        self.assertIsNone(latest_numeric_series_value(None))

    def test_wan_common_is_primary_physical_wan_evidence(self):
        fc = FakeFritzConnection(access_type="Ethernet")
        adapter = FritzAdapter(
            "192.0.2.1",
            "u",
            "p",
            connection_factory=self.factory(fc),
            temp_interval=0,
        )
        snapshot, log = adapter.snapshot()
        self.assertEqual(snapshot["wan_access_type"], "Ethernet")
        self.assertEqual(snapshot["wan_physical_status"], "Up")
        self.assertEqual(snapshot["wan_down_bytes_s"], 321.0)
        self.assertEqual(snapshot["wan_up_bytes_s"], 45.0)
        self.assertEqual(snapshot["wan_sync_group"], "sync_ata")
        self.assertEqual(snapshot["wan_sync_mode"], "ATA")
        self.assertEqual(snapshot["router_cpu_temp_c"], 107.0)
        self.assertEqual(log, "log")

    def test_online_monitor_fallback_uses_ds_not_multicast_and_latest_sample(self):
        fc = FakeFritzConnection(access_type="Ethernet", common_utilization=False)
        adapter = FritzAdapter(
            "192.0.2.1",
            "u",
            "p",
            connection_factory=self.factory(fc),
            temp_interval=0,
        )
        snapshot, _ = adapter.snapshot()
        self.assertEqual(snapshot["wan_down_bytes_s"], 300.0)
        self.assertEqual(snapshot["wan_up_bytes_s"], 30.0)

    def test_fiber_service_presence_does_not_mean_active_fiber(self):
        fc = FakeFritzConnection(access_type="Ethernet")
        adapter = FritzAdapter(
            "192.0.2.1", "u", "p", connection_factory=self.factory(fc), temp_interval=0
        )
        snapshot, _ = adapter.snapshot()
        self.assertIsNone(snapshot["fiber_rx_dbm"])
        self.assertFalse(
            any(service == "X_AVM-DE_WANFiber1" for service, _, _ in fc.calls)
        )

    def test_active_fiber_collects_only_diagnostic_fields(self):
        fc = FakeFritzConnection(access_type="X_AVM-DE_Fiber")
        adapter = FritzAdapter(
            "192.0.2.1", "u", "p", connection_factory=self.factory(fc), temp_interval=0
        )
        snapshot, _ = adapter.snapshot()
        self.assertEqual(snapshot["fiber_rx_dbm"], -18.25)
        self.assertEqual(snapshot["fiber_tx_dbm"], 2.15)
        self.assertEqual(snapshot["fiber_mode"], "GPON")
        self.assertEqual(snapshot["fiber_resyncs"], 2)
        self.assertEqual(snapshot["fiber_errors_rx"], 3)
        self.assertEqual(snapshot["fiber_errors_tx"], 4)
        self.assertNotIn("sfp_serial", snapshot)
        self.assertNotIn("gpon_serial", snapshot)


if __name__ == "__main__":
    unittest.main()
