#!/usr/bin/env python3

import os
import time
import subprocess
import requests
import sys
from gigablast import GigablastAPI
from junit_xml import TestSuite, TestCase


class TestRunner:
    def __init__(self, testdir, testcase, gb_path, gb_host, gb_port, ws_scheme, ws_domain, ws_port):
        self.testcase = testcase
        self.testcasedir = os.path.join(testdir, testcase)
        self.testcaseconfigdir = os.path.join(self.testcasedir, 'testcase')

        self.gb_path = gb_path
        self.gb_starttime = 0

        self.api = GigablastAPI(gb_host, gb_port)

        self.ws_scheme = ws_scheme
        self.ws_domain = ws_domain
        self.ws_port = ws_port

        self.testcases = []

    def run_test(self):
        # verify we have testcase to run
        if os.path.exists(self.testcaseconfigdir):
            # verify gb has started
            if self.start_gb():
                # seed gb
                self.seed()

                # verify gb has done spidering (only run other test if spidering is successful)
                if self.wait_spider_done():
                    # search
                    self.just_search()

                    # verify indexed
                    self.verify_indexed()

                    # verify not indexed
                    self.verify_not_indexed()

                # stop & cleanup
                self.stop_gb()

        return self.get_testsuite()

    @staticmethod
    def read_file(filename):
        if os.path.exists(filename):
            with open(filename, 'r') as file:
                return file.read().splitlines()

        return []

    def start_gb(self):
        print('Cleaning old data')
        subprocess.call(['make', 'cleantest'], cwd=self.gb_path, stdout=subprocess.DEVNULL)

        print('Starting gigablast')
        start_time = time.perf_counter()

        subprocess.call(['./gb', 'start'], cwd=self.gb_path, stdout=subprocess.DEVNULL)

        # wait until started
        result = True
        while result:
            try:
                self.update_processuptime()
                break
            except requests.exceptions.ConnectionError as e:
                # wait for a max of 300 seconds
                if time.perf_counter() - start_time > 300:
                    result = False
                    break
                time.sleep(0.5)

        # set some default config
        self.config_gb()

        self.add_testcase('gb_start', start_time, not result)
        return result

    def save_gb(self):
        print('Saving gigablast')
        subprocess.call(['./gb', 'save'], cwd=self.gb_path, stderr=subprocess.DEVNULL)

        # wait for gb mode to be updated
        time.sleep(0.5)

    def stop_gb(self):
        print('Stopping gigablast')
        subprocess.call(['./gb', 'stop'], cwd=self.gb_path, stderr=subprocess.DEVNULL)

    def config_gb(self):
        self.api.config_crawldelay(0, 0)
        self.api.config_dns('127.0.0.1')

    def seed(self):
        print('Adding seed for spidering')
        filename = os.path.join(self.testcaseconfigdir, 'seeds')
        items = self.read_file(filename)
        seedstr = ""
        if len(items) == 0:
            # default seed
            for entry in os.scandir(self.testcasedir):
                if entry.is_dir() and entry.name != 'testcase':
                    seedstr += "{}://{}.{}.{}:{}/\n".format(self.ws_scheme, entry.name, self.testcase,
                                                            self.ws_domain, self.ws_port)
        else:
            for item in items:
                seedstr += item.format(SCHEME=self.ws_scheme, DOMAIN=self.ws_domain, PORT=self.ws_port) + '\n'

        seedstr = seedstr.rstrip('\n')
        self.api.config_sitelist(seedstr)

    def wait_spider_done(self):
        print('Waiting for spidering to complete')
        start_time = time.perf_counter()

        # wait until
        #   - spider is in progress
        #   - waitingTree spider time is more than an hour
        #   - no pending doleIP
        #   - nothing is being spidered
        result = True
        while result:
            try:
                response = self.api.get_spiderqueue()['response']
            except:
                result = False
                break

            if response['statusCode'] == 7 and response['doleIPCount'] == 0 and response['spiderCount'] == 0:
                if response['waitingTreeCount'] > 0:
                    has_pending_spider = False
                    for waiting_tree in response['waitingTrees']:
                        if waiting_tree['spiderTime'] < ((time.time() + 3600) * 1000):
                            has_pending_spider = True

                    if not has_pending_spider:
                        self.save_gb()
                        break

            # wait for a max of 300 seconds
            if time.perf_counter() - start_time > 300:
                result = False
                break

            time.sleep(0.5)

        self.add_testcase('gb_spider', start_time, not result)
        return result

    def add_testcase(self, test_name, start_time, failed=False):
        testcase = TestCase(test_name, elapsed_sec=(time.perf_counter() - start_time))
        if failed:
            testcase.add_failure_info(test_name + ' - failed')

        if not self.validate_processuptime():
            testcase.add_failure_info(test_name + ' - gb restarted')
            self.update_processuptime()

        self.testcases.append(testcase)

    def get_testsuite(self):
        return TestSuite(self.testcase, self.testcases)

    def validate_processuptime(self):
        return self.api.status_processstarttime() == self.gb_starttime

    def update_processuptime(self):
        self.gb_starttime = self.api.status_processstarttime()

    def just_search(self):
        test_type = 'just_search'
        print('Running test -', test_type)
        filename = os.path.join(self.testcaseconfigdir, test_type)
        items = self.read_file(filename)
        for index, item in enumerate(items):
            start_time = time.perf_counter()
            try:
                response = self.api.search(item)
                self.add_testcase(test_type + ' - ' + item, start_time)
            except:
                self.add_testcase(test_type + ' - ' + item, start_time, True)

    def verify_indexed(self):
        test_type = 'verify_indexed'
        print('Running test -', test_type)
        filename = os.path.join(self.testcaseconfigdir, test_type)
        items = self.read_file(filename)
        for index, item in enumerate(items):
            start_time = time.perf_counter()
            try:
                response = self.api.search(item)
                self.add_testcase(test_type + ' - ' + item, start_time, (not len(response['results']) != 0))
            except:
                self.add_testcase(test_type + ' - ' + item, start_time, True)

    def verify_not_indexed(self):
        test_type = 'verify_not_indexed'
        print('Running test -', test_type)
        filename = os.path.join(self.testcaseconfigdir, test_type)
        items = self.read_file(filename)
        for index, item in enumerate(items):
            start_time = time.perf_counter()
            try:
                response = self.api.search(item)
                self.add_testcase(test_type + ' - ' + item, start_time, (not len(response['results']) == 0))
            except:
                self.add_testcase(test_type + ' - ' + item, start_time, True)


def main(testdir, testcase, gb_path, gb_host, gb_port, ws_scheme, ws_domain, ws_port):
    test_runner = TestRunner(testdir, testcase, gb_path, gb_host, gb_port, ws_scheme, ws_domain, ws_port)
    test_runner.run_test()


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('testcase', help='Test case to run')
    parser.add_argument('--testdir', dest='testdir', default='tests', action='store',
                        help='Directory containing test cases')

    default_gbpath = os.path.normpath(os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                                   '../open-source-search-engine'))
    parser.add_argument('--path', dest='gb_path', default=default_gbpath, action='store',
                        help='Directory containing gigablast binary (default: {})'.format(default_gbpath))
    parser.add_argument('--host', dest='gb_host', default='127.0.0.1', action='store',
                        help='Gigablast host (default: 127.0.0.1)')
    parser.add_argument('--port', dest='gb_port', default='28000', action='store',
                        help='Gigablast port (default: 28000')

    parser.add_argument('--dest-scheme', dest='ws_scheme', default='http', action='store',
                        help='Destination host scheme (default: 127.0.0.1)')
    parser.add_argument('--dest-domain', dest='ws_domain', default='privacore.test', action='store',
                        help='Destination host domain (default: privacore.test)')
    parser.add_argument('--dest-port', dest='ws_port', type=int, default=28080, action='store',
                        help='Destination host port (default: 28080')

    args = parser.parse_args()

    main(args.testdir, args.testcase, args.gb_path, args.gb_host, args.gb_port,
         args.ws_scheme, args.ws_domain, args.ws_port)