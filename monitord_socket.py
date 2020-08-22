#!/usr/bin/python3
import socket, time, sys, threading, subprocess
import logbook
from logbook import Logger, StreamHandler, MonitoringFileHandler
from datetime import datetime, time as dtime
import requests
import pprint
import json

class MonitordSocketClient:
    lastAlert_time = 0.0
    lastAlert_zvei = "0"
    logger = 0

    def __init__(self):
        self.loadConfig()

    def loadConfig(self):
        with open("config.json") as config_file:
            config = json.load(config_file)
            if len(config["config"]) != 7:
                raise Exception("Please check config file. Wrong count of config options")
            if len(config["trigger"]) == 0:
                raise Exception("Please check config file. No trigger defined")
            self.config = config["config"]
            self.triggers = config["trigger"]

    def startNewDataThread(self, data):
        x = threading.Thread(target=self.processData, args=(data,))
        x.start()

    def processData(self, raw_data):
        data = raw_data.split(":")
        if data[0] == "100":
            self.logger.info("Received welcome. MonitorD version: " + data[1])
        elif data[0] == "300":
            self.newAlert(data[3])
        else:
            self.logger.error("Received unknown command. Command: " + repr(raw_data))
        return

    def newAlert(self, zvei):
        if self.checkIfDoubleAlert(zvei):
            return
        self.logger.info("{}Received alarm.".format("[" + str(zvei) + "]: "))
        subprocess.check_output(
            '/usr/bin/zabbix_sender -c /etc/zabbix/zabbix_agentd.conf -k "receivedZVEI" -o "' + str(zvei) + '"',
            shell=True)

        trigger = self.checkIfAlertinFilter(zvei)
        if not trigger:
            self.logger.info("{}Received alarm not in filter. Stopping...".format("[" + str(zvei) + "]: "))
            return
        self.logger.info("{}!!!Received alarm in filter {} (Time: {}) Starting...".format("[" + str(zvei) + "]: ", trigger["name"], str(datetime.now().time())))
        if self.isTestAlert(trigger):
            self.logger.info("{}Testalart time. Stopping...".format("[" + str(zvei) + "]: "))
            return
        self.logger.info("{}Start alarm tasks...".format("[" + str(zvei) + "]: "))
        self.doAlertThings(zvei, trigger)
        return

    def checkIfDoubleAlert(self, zvei):
        double_alert = False

        if zvei == self.lastAlert_zvei:
            if time.time() - self.lastAlert_time < 10:
                double_alert = True

        self.lastAlert_time = time.time()
        self.lastAlert_zvei = zvei

        return double_alert

    def checkIfAlertinFilter(self, zvei):
        for key, config in self.triggers:
            if key == zvei:
                return config
        return False

    def isTestAlert(self, trigger):
        begin_time = dtime(trigger["hour_start"], trigger["minute_start"])
        end_time = dtime(trigger["hour_end"], trigger["minute_end"])
        check_time = datetime.now().time()
        return datetime.today().weekday() == trigger["weekday"] and check_time >= begin_time and check_time <= end_time

    def doAlertThings(self, zvei, trigger):
        payload = trigger["request"]
        for request_try in range(self.config["retries"]):
            r = requests.get(self.config["url"], params=payload)
            self.logger.debug(pprint.saferepr(r.url))
            self.logger.debug(pprint.saferepr(r.status_code))
            self.logger.debug(pprint.saferepr(r.content))
            self.logger.debug(pprint.saferepr(r.headers))
            if not r.status_code == requests.codes.ok:
                self.logger.error("{}Failed to send alert. Try: {}/{}".format("[" + str(zvei) + "]: ", str(request_try + 1), str(self.config["retries"])))
                time.sleep(self.config["retry_delay"])
                continue
            else:
                self.logger.info("{}Successfully send alert".format("[" + str(zvei) + "]: "))
                break


        if trigger["local"]:
            try:
                self.logger.info("Starting light control")
                debugOutput = subprocess.check_output('/usr/bin/python3 /opt/light/FFWLightControlTrigger.py', shell=True)
                self.logger.debug(pprint.saferepr(debugOutput))
            except:
                self.logger.error("Light control exception")

            try:
                self.logger.info("Starting TV control")
                subprocess.check_output('/usr/bin/php /usr/local/bin/automate_tv 900 &', shell=True)
            except:
                self.logger.info("TV control exception")

        return

    def reportConnectionError(self, count):
        self.logger.error("Connection Error Count:" + count)
        return

    def main(self):
        logbook.set_datetime_format("local")
        StreamHandler(sys.stdout, level=self.config["loglevel"]).push_application()
        MonitoringFileHandler(self.config["logpath"], mode='a', encoding='utf-8', bubble=True,
                              level=self.config["loglevel"]).push_application()
        self.logger = Logger('monitord_socket.py')

        self.logger.info("starting...")
        connectionErrorCount = 0
        while True:
            self.logger.info('Connection to {}:{}'.format(self.config["host"], self.config["port"]))
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                s.connect((self.config["host"], self.config["port"]))
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
