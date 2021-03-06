# Copyright 2018 The Pontem Authors. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Wrapper for Cloud SQL API service proxy."""

import uuid

from googleapiclient import errors
from httplib2 import HttpLib2Error

import google.auth

from google.cloud.pontem.sql.replicator.util import gcp_api_util

# Defaults for Cloud SQL instances
DEFAULT_1ST_GEN_DB_VERSION = 'MYSQL_5_6'
DEFAULT_2ND_GEN_DB_VERSION = 'MYSQL_5_7'
DEFAULT_1ST_GEN_TIER = 'd2'
DEFAULT_2ND_GEN_TIER = 'db-n1-standard-2'
DEFAULT_1ST_GEN_REGION = 'us-central'
DEFAULT_2ND_GEN_REGION = 'us-central1'
DEFAULT_REPLICATION_PORT = '3306'
DEFAULT_CLOUDSQL_FORMAT_STRING = 'cloudsql-db-{}'
DEFAULT_EXT_MASTER_FORMAT_STRING = 'external-mysql-representation-{}'
DEFAULT_REPLICA_FORMAT_STRING = 'cloudsql-replica-{}'

# Cloud SQL Service
SQL_ADMIN_SERVICE = 'sqladmin'
SQL_ADMIN_SERVICE_VERSION = 'v1beta4'

# Response Attributes
IP_ADDRESSES = 'ipAddresses'
IP_ADDRESS = 'ipAddress'
SERVICE_ACCOUNT_EMAIL = 'serviceAccountEmailAddress'

# Validation
SUPPORTED_VERSIONS = frozenset({'MYSQL_5_6', 'MYSQL_5_7'})


def build_sql_admin_service(credentials=None):
    """Builds Cloud SQL service proxy with custom user agent.

      Args:
        credentials (google.auth.Credentials): Credentials to authorize client

      Returns:
        Resource: Authorized sqladmin service proxy with custom user agent.
    """
    default_credentials, _ = google.auth.default()
    service = gcp_api_util.build_authorized_service(
        SQL_ADMIN_SERVICE,
        SQL_ADMIN_SERVICE_VERSION,
        credentials or default_credentials
    )

    return service


def create_cloudsql_instance(database_instance_body=None,
                             project=None,
                             credentials=None):
    """Provisions a Cloud SQL instance.

      Args:
        database_instance_body(JSON): Cloud SQL instance creation options.
        project(str): Project ID where Cloud SQL instance will be created.
        credentials (google.auth.Credentials): Credentials to authorize client.

      Returns:
        JSON: response from sqladmin.instances().insert() call
    """

    default_credentials, default_project = google.auth.default()
    default_database_instance_body = {
        'name': DEFAULT_CLOUDSQL_FORMAT_STRING.format(uuid.uuid4()),
        'settings': {
            'tier': DEFAULT_2ND_GEN_TIER
        }
    }
    service = build_sql_admin_service(credentials or default_credentials)
    request = service.instances().insert(
        project=project or default_project,
        body=database_instance_body or default_database_instance_body
    )
    response = request.execute()

    return response


def create_source_representation(
        ip_address=None,
        port=DEFAULT_REPLICATION_PORT,
        database_version=DEFAULT_2ND_GEN_DB_VERSION,
        region=DEFAULT_2ND_GEN_REGION,
        source_name=None,
        source_body=None,
        project=None,
        credentials=None):
    """Creates a source representation of an external master.


    If source_body is included source_representation_name,
    ip_address, port, db_version and region are ignored.

    Args:
      source_name (str): The instance name of the
        external master.
      ip_address (str): The ip address of the external master.
      port (str): Port that will be used for replication.
      region (str): Region source representation will be created.
      database_version (str): MySQL database version
      source_body (JSON): Creation options for source
        representation.
      project (str): Project ID where replica will be created.
      credentials (google.auth.Credentials): Credentials to authorize
        client.

    Returns:
        JSON: response from sqladmin.instances().insert() call.
    """
    default_source_body = {
        'name': (source_name or
                 DEFAULT_EXT_MASTER_FORMAT_STRING.format(uuid.uuid4())),
        'databaseVersion': database_version,
        'region': region,
        'onPremisesConfiguration': {
            'kind': 'sql#onPremisesConfiguration',
            'hostPort': '{}:{}'.format(ip_address, port)
        }

    }

    response = create_cloudsql_instance(
        source_body or default_source_body,
        project,
        credentials
    )

    return response


def create_replica_instance(
        master_instance_name=None,
        dumpfile_path=None,
        replica_user=None,
        replica_pwd=None,
        replica_name=None,
        replica_body=None,
        project=None,
        credentials=None):
    """Provisions a Cloud SQL Replica instance.

      Will create a second generation replica by default, specify tier and
      region if creating a first generation replica.

      If replica_instance_body is supplied, master_instance_name, dumpfile_path
        replica_user, replica_pwd, and replica_instance_name will be ignored.

      Args:
        master_instance_name (str): Instance name of master that will be
          replicated.
        dumpfile_path (str): SQL file path (possibly gzipped) that contains dump
          from master.
        replica_user (str): User name of replica user.
        replica_pwd (str): Password of replica user.
        replica_name (str): Name of replica instance to create.
        replica_body (JSON): Options for replica instance creation.
        project (str): Project ID where replica will be created.
        credentials (google.auth.Credentials): Credentials to authorize client

      Returns:
        JSON: response from sqladmin.instances().insert() call
    """

    default_replica_body = {
        'name': replica_name or
                DEFAULT_REPLICA_FORMAT_STRING.format(uuid.uuid4()),
        'settings': {
            'tier': DEFAULT_2ND_GEN_TIER,

        },
        'databaseVersion': DEFAULT_2ND_GEN_DB_VERSION,
        'masterInstanceName': master_instance_name,
        'region': DEFAULT_2ND_GEN_REGION,
        'replicaConfiguration': {
            'mysqlReplicaConfiguration': {
                'dumpFilePath': dumpfile_path,
                'username': replica_user,
                'password': replica_pwd,
            }

        }
    }

    response = create_cloudsql_instance(
        replica_body or default_replica_body,
        project,
        credentials
    )

    return response


def import_sql_database(database_instance,
                        import_file_uri,
                        project=None,
                        credentials=None):
    """Import database from SQL import file.

      Args:
        database_instance (str): Database instance id.
        import_file_uri (str): URI of sql file to import.
        project(str): Project ID
        credentials (google.auth.Credentials): Credentials to authorize client.

      Returns:
        JSON: response from sqladmin.instances().insert() call.
    """
    default_credentials, default_project = google.auth.default()
    service = build_sql_admin_service(credentials or default_credentials)
    instances_import_request_body = {
        'importContext': {
            'kind': 'sql#importContext',
            'fileType': 'SQL',
            'uri': import_file_uri,
        }
    }

    request = service.instances().import_(
        project=project or default_project,
        instance=database_instance,
        body=instances_import_request_body
    )
    response = request.execute()

    return response


def is_sql_operation_done(operation, project=None, credentials=None):
    """Returns True if a SQL operation is done.

    Args:
        operation (str): operation id to check.
        project (str): Project ID
        credentials (google.auth.Credentials): Credentials to authorize client.

    Returns:
          bool: whether operation is done.
    """
    default_credentials, default_project = google.auth.default()
    service = build_sql_admin_service(credentials or default_credentials)
    request = service.operations().get(
        project=project or default_project,
        operation=operation)
    response = request.execute()

    return response['status'] == 'DONE'


def get_instance(instance, project=None, credentials=None):
    """Returns information about Cloud SQL instance.

    Args:
        instance (str): name of instance to get IP address from.
        project (str): Project ID
        credentials (google.auth.Credentials): Credentials to authorize client.

    Returns:
        JSON: Resource describing Cloud SQL instance.

    Raises:
        NameError: Exception if instance is not found.
    """
    default_credentials, default_project = google.auth.default()
    service = build_sql_admin_service(credentials or default_credentials)
    request = service.instances().get(
        project=project or default_project,
        instance=instance)

    try:
        return request.execute()
    except (errors.HttpError, HttpLib2Error) as e:
        if isinstance(e, errors.HttpError) and e.resp.status == 404:
            raise NameError('Cloud SQL instance {} not found.'.format(instance))


def get_outgoing_ip_of_instance(instance, project=None, credentials=None):
    """Returns outgoing IP address of Cloud SQL instance.

    Args:
       instance (str): name of instance to get IP address from.
       project (str): Project ID
       credentials (google.auth.Credentials): Credentials to authorize client.

    Returns:
       str: IP address of SQL instance.

    Raises:
       KeyError: Exception if no OUTGOING IP Address is not found.
    """
    response = get_instance(instance, project, credentials)

    if IP_ADDRESSES in response:
        outgoing_ip_address = (
            next(
                ip_address for ip_address in response[IP_ADDRESSES]
                if ip_address['type'] == 'OUTGOING'
            )
        )
        if outgoing_ip_address:
            return outgoing_ip_address[IP_ADDRESS]
        raise KeyError('No outgoing IP address found.')

    raise KeyError('{} not found in response.'.format(IP_ADDRESSES))


def get_ip_and_service_account(instance, project=None, credentials=None):
    """Gets both the outgoing ip address and service accont of an instance.

    Args:
       instance (str): name of instance to get IP address from.
       project (str): Project ID
       credentials (google.auth.Credentials): Credentials to authorize client.

    Returns:
       str: IP address of SQL instance.
       str: Service account email.
    """
    response = get_instance(instance, project, credentials)
    ip_address = None
    service_account = None
    if IP_ADDRESSES in response:
        outgoing_ip_address = (
            next(
                ip_address for ip_address in response[IP_ADDRESSES]
                if ip_address['type'] == 'OUTGOING'
            )
        )
        if outgoing_ip_address:
            ip_address = outgoing_ip_address[IP_ADDRESS]
    if SERVICE_ACCOUNT_EMAIL in response:
        service_account = response[SERVICE_ACCOUNT_EMAIL]

    return ip_address, service_account
