import requests
import re
from subprocess import Popen, PIPE, STDOUT
import logging
from logging.handlers import RotatingFileHandler
import sys
from socket import gethostname
import ConfigParser
import io
import os

api_address = ""
api_port = ""
hosts_path = ""
hostname_path = ""
domain_name = ""
log_path = ""
config_ini = os.path.join(os.path.dirname(__file__), 'config.ini')


def get_config(conf_file):
    with open(conf_file) as f:
        config_file = f.read()
    config = ConfigParser.RawConfigParser(allow_no_value=True)
    config.readfp(io.BytesIO(config_file))

    global api_address
    global api_port
    global hosts_path
    global hostname_path
    global domain_name
    global log_path

    api_address = config.get('api', 'api_address')
    api_port = config.get('api', 'api_port')
    hosts_path = config.get('file paths', 'hosts_path')
    hostname_path = config.get('file paths', 'hostname_path')
    domain_name = config.get('environment', 'domain_name')
    log_path = config.get('logging', 'log_path')


class ContextFilter(logging.Filter):
    hostname = gethostname()

    def filter(self, record):
        record.hostname = ContextFilter.hostname
        return True


def get_projects():
    url = 'http://%s:%s/v2/projects' % (api_address, api_port)

    try:
        r = requests.get(url, timeout=10)
    except requests.exceptions.RequestException as e:
        logger.error('Error connecting to GNS3 API: %s' % e)
        exit()

    if r.status_code == 200:

        projects_list = []

        json_file = r
        projects = json_file.json()

        for project in projects:
            projects_list.append(project['project_id'])

        return projects_list

    else:
        logger.error('GNS3 API returned none 200 response')
        exit()


def get_nodes(project_ids):

    nodes_dict = {}

    for id in project_ids:

        try:
            url = "http://%s:%s/v2/projects/%s/nodes" % (api_address, api_port, id)
        except requests.exceptions.RequestException as e:
            logger.error('Error connecting to GNS3 API: %s' % e)
            exit()

        r = requests.get(url, timeout=10)

        if r.status_code == 200:
            nodes = r.json()

            for node in nodes:
                nodes_dict[node['node_id']] = node['name']
        else:
            logger.error('GNS3 API returned none 200 response')
            exit()

    return nodes_dict


def get_node():

    cmd = 'dmidecode | grep -i uuid'
    p = Popen(cmd, shell=True, stdin=PIPE, stdout=PIPE, stderr=STDOUT, close_fds=True)
    output = p.stdout.read()

    m = re.search('\s*UUID:\s(.*)$', output)
    if m:
        found = m.group(1)
        return found.lower()
    else:
        return


def get_host_hostname():
    cmd = 'hostname -s'
    p = Popen(cmd, shell=True, stdin=PIPE, stdout=PIPE, stderr=STDOUT, close_fds=True)
    output = p.stdout.read().rstrip('\n')
    return output


def get_gns3_hostname(node, nodes):
    hostname = nodes[node].lower()
    return hostname


def update_hostname(path, gns3_host, host_host):

    hostname_lines = []
    updated = 0

    with open(path, "r") as f:
        for line in f:
            hostname_lines.append(line.rstrip('\n'))
    f.close()

    for n, line in enumerate(hostname_lines):
        m = re.search('^(.*)$', line)
        if m.group(1) != gns3_host:
            with open(path, "w") as f:
                f.write(gns3_host + '\n')
            f.close()
            updated = 1

    if host_host != gns3_host:
        cmd = 'hostname %s' % gns3_host
        p = Popen(cmd, shell=True, stdin=PIPE, stdout=PIPE, stderr=STDOUT, close_fds=True)
        updated = 1

    return updated


def update_hosts_file(path, host, domain):

    fqdn = "%s.%s" % (host, domain)
    hosts_lines = []
    updated = 0

    with open(path, "r") as f:
        for line in f:
            hosts_lines.append(line.rstrip('\n'))
    f.close()

    for n, line in enumerate(hosts_lines):
        m = re.search('^127.0.1.1\t(.*?)\t(.*)$', line)
        if m:
            if m.group(1) != fqdn or m.group(2) != host:
                hosts_lines[n] = '127.0.1.1\t%s\t%s' % (fqdn, host)
                with open(path, "w") as f:
                    for each in hosts_lines:
                         f.write(each + '\n')
                f.close()
                updated = 1
    return updated


def exit():
    logger.info('GNS3-Hostname-Grabber has stopped')
    sys.exit(1)

def init_logging():

    global logger

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(log_path, maxBytes=10000000, backupCount=5)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s %(hostname)s GNS3-Hostname-Grabber: [%(levelname)s] %(message)s',
                                  datefmt='%Y-%m-%d %H:%M:%S')
    handler.setFormatter(formatter)
    f = ContextFilter()
    handler.addFilter(f)
    logger.addHandler(handler)


def main():

    get_config(config_ini)
    init_logging()

    logger.info('GNS3-Hostname-Grabber is running')

    node = get_node()
    projects = get_projects()
    nodes = get_nodes(projects)
    gns3_hostname = get_gns3_hostname(node, nodes)
    host_hostname = get_host_hostname()

    logger.info("GNS3 API reports hostname as %s" % gns3_hostname)
    logger.info("Host reports hostname as %s" % host_hostname)


    if update_hosts_file(hosts_path, gns3_hostname, domain_name):
        logger.info("Hostname has changed, hosts file updated!")
    else:
        logger.info("No change to hosts file, nothing to do.")

    if update_hostname(hostname_path, gns3_hostname, host_hostname):
        logger.info("Hostname has changed, hostname updated!")
    else:
        logger.info("No change to hostname, nothing to do.")

    logger.info('GNS3-Hostname-Grabber has stopped')

if __name__ == "__main__":
    main()