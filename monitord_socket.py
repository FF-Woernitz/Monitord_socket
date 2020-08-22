#!/usr/bin/python3
import socket, time, sys, threading, subprocess
import logbook
from logbook import Logger, StreamHandler, MonitoringFileHandler
from datetime import datetime, time as dtime
import requests
import pprint
import json

class MonitordSocketClient:

    HOST = '127.0.0.1'
    PORT = 9333

    LOGLEVEL = 'INFO'

    FILTER_LIST = ["27835"]
    DIVERA_KEY = ""


    lastAlert_time = 0.0
    lastAlert_zvei = "0"

    logger = 0

    def processData(self, raw_data):
        data = raw_data.split(":")
        if data[0] == "100":
            self.logger.info("Received welcome. MonitorD version: " + data[1])
        elif data[0] == "300":
            self.newAlert(data[3])
        else:
            self.logger.error("Received unknown command. Command: " + repr(raw_data))
        return


    def startNewDataThread(self, data):
        x = threading.Thread(target=self.processData, args=(data,))
        x.start()

    def checkIfDoubleAlert(self, zvei):
        double_alert = False

        if zvei == self.lastAlert_zvei:
            if time.time() - self.lastAlert_time < 10:
                double_alert = True

        self.lastAlert_time = time.time()
        self.lastAlert_zvei = zvei

        return double_alert

    def checkIfAlertinFilter(self, zvei):

        for x in self.FILTER_LIST:
            if x == zvei:
                return True
        return False

    def isTestAlert(self):
        begin_time = dtime(12,10)
        end_time = dtime(12,25)
        check_time = datetime.now().time()
        return datetime.today().weekday() == 5 and check_time >= begin_time and check_time <= end_time

    def newAlert(self, zvei):
        if self.checkIfDoubleAlert(zvei):
            return
        self.logger.info("Received alarm. ZVEI: " + zvei)
        subprocess.check_output('/usr/bin/zabbix_sender -c /etc/zabbix/zabbix_agentd.conf -k "receivedZVEI" -o "' + str(zvei) + '"', shell=True)

        if not self.checkIfAlertinFilter(zvei):
            self.logger.info("Received alarm not in filter. Stopping...")
            return
        self.logger.info("!!!Received alarm in filter!!! (Time: " + str(datetime.now().time()) + ") Starting...")
        if self.isTestAlert():
            self.logger.info("Testalart time. Stopping...")
            return
        self.logger.info("Start alarm tasks...")
        self.doAlertThings(zvei)
        return

    def doAlertThings(self, zvei):
        payload = {'accesskey': self.DIVERA_KEY, 'type': 'Einsatz'}
        r = requests.get("https://www.divera247.com/api/alarm", params=payload)
        if not r.status_code == requests.codes.ok:
            self.logger.error("Received bad status code. Code: " + str(r.status_code))
        self.logger.info("Received status code. Code: " + str(r.status_code))
        #self.logger.debug(pprint.saferepr(r.content))  #DEBUG
        #self.logger.debug(pprint.saferepr(r.headers))  #DEBUG
        #self.logger.debug(pprint.saferepr(r.params))  #DEBUG

        try:
            self.logger.info("Starting light control")
            debugOutput = subprocess.check_output('/usr/bin/python3 /opt/light/FFWLightControlTrigger.py', shell=True)
            self.logger.debug(pprint.saferepr(debugOutput))
        except:
            self.logger.error("Light control exception")

        try:
            self.logger.info("Starting TV control")
            debugOutput = subprocess.check_output('/usr/bin/php /usr/local/bin/automate_tv 900 &', shell=True)
            self.logger.debug(pprint.saferepr(debugOutput))
        except:
            self.logger.info("TV control exception")

        return

    def reportConnectionError(self,count):
        self.logger.error("Connection Error Count:" + count)
        return


    def main(self):
        logbook.set_datetime_format("local")
        StreamHandler(sys.stdout, level=self.LOGLEVEL).push_application()
        MonitoringFileHandler('/var/log/monitord_socket.log', mode='a', encoding='utf-8', bubble=True, level=self.LOGLEVEL).push_application()
        self.logger = Logger('monitord_socket.py')

        self.logger.info("starting...")
        connectionErrorCount = 0
        while True:
            self.logger.info('Connection to {}:{}'.format(self.HOST, self.PORT))
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                s.connect((self.HOST, self.PORT))
            except:
                connectionErrorCount += 1
                self.reportConnectionError(connectionErrorCount)
                time.sleep(10)
                continue
            connectionErrorCount = 0
            try:
                while True:
                    data = s.recv(1024)
                    if data:
                        self.logger.debug('Received => ' + repr(data))
                        self.startNewDataThread(data.decode('ascii'))
                    else:
                        self.logger.warning('Connection lost! Restarting...')
                        break
            except KeyboardInterrupt:
                print("\nShutting down...")
                self.logger.warning('Shutting down...')
                exit()
            s.close()
            time.sleep(5)

if __name__ == '__main__':
    c = MonitordSocketClient()
    c.main()
