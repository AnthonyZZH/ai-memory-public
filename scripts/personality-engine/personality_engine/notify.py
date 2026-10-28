"""Best-effort Windows 5.1 toast. Only dimensions and deltas leave the engine."""
import base64
import os
import subprocess
import xml.etree.ElementTree as ET


def pending(config, proposals):
    if not config.data.get('notifications', {}).get('enabled', False) or os.name != 'nt':
        return False
    try:
        toast = ET.Element('toast')
        binding = ET.SubElement(ET.SubElement(toast, 'visual'), 'binding', template='ToastGeneric')
        ET.SubElement(binding, 'text').text = '性格变化待批准'
        ET.SubElement(binding, 'text').text = '、'.join(p['trait'] + ' ' + format(p['delta'], '+d') for p in proposals)
        payload = base64.b64encode(ET.tostring(toast, encoding='utf-8')).decode('ascii')
        script = ("$ErrorActionPreference='Stop';"
                  "[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime]>$null;"
                  "[Windows.Data.Xml.Dom.XmlDocument,Windows.Data.Xml.Dom.XmlDocument,ContentType=WindowsRuntime]>$null;"
                  "$xml=New-Object Windows.Data.Xml.Dom.XmlDocument;"
                  "$xml.LoadXml([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + payload + "')));"
                  "$toast=[Windows.UI.Notifications.ToastNotification]::new($xml);"
                  "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Microsoft.Windows.PowerShell').Show($toast)")
        encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden',
                                 '-EncodedCommand', encoded], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                timeout=10, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return result.returncode == 0
    except Exception:
        return False
