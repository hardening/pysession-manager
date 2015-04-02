# _WTS_INFO_CLASS
WTSInitialProgram, WTSApplicationName, WTSWorkingDirectory, WTSOEMId, \
    WTSSessionId, WTSUserName, WTSWinStationName, WTSDomainName, WTSConnectState, WTSClientBuildNumber, \
    WTSClientName, WTSClientDirectory, WTSClientProductId, \
    WTSClientHardwareId, WTSClientAddress, WTSClientDisplay, \
    WTSClientProtocolType, WTSIdleTime, WTSLogonTime, WTSIncomingBytes, WTSOutgoingBytes, \
    WTSIncomingFrames, WTSOutgoingFrames, WTSClientInfo, WTSSessionInfo, \
    WTSSessionInfoEx, WTSConfigInfo, WTSValidationInfo, WTSSessionAddressV4, \
    WTSIsRemoteSession = range(0, 30)

# _WTS_CONNECTSTATE_CLASS
WTSActive, WTSConnected, WTSConnectQuery, WTSShadow, WTSDisconnected, WTSIdle, \
    WTSListen, WTSReset, WTSDown, WTSInit = range(0, 10)
