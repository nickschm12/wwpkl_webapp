from google.cloud import secretmanager
import json
import os
import sqlalchemy

def get_secrets():
    project_id = os.environ.get('PROJECT_ID')
    db_secret_id = os.environ.get('DB_SECRET_ID')
    db_secret_version = os.environ.get('DB_SECRET_VERSION')

    client = secretmanager.SecretManagerServiceClient()
    secret_name = f"projects/{project_id}/secrets/{db_secret_id}/versions/{db_secret_version}"
    response = client.access_secret_version(request={"name": secret_name})
    payload = response.payload.data.decode("UTF-8")
    return json.loads(payload)

def unix_connection():
    secrets = get_secrets()

    host = "/cloudsql/{}".format(secrets['db_connection_name'])

    engine = sqlalchemy.create_engine(
        sqlalchemy.engine.url.URL(
            drivername='postgresql',
            username=secrets['db_user'],
            password=secrets['db_pw'],
            query={ 'host': host }
        )
    )

    return engine

def tcp_connection():
    # Extract host and port from db_host
    db_host = os.environ.get('DB_HOST')
    host_args = db_host.split(":")
    db_hostname, db_port = host_args[0], int(host_args[1])

    secrets = get_secrets()

    engine = sqlalchemy.create_engine(
        sqlalchemy.engine.url.URL(
            drivername='postgresql',
            username=secrets['db_user'],
            password=secrets['db_pw'],
            host=db_hostname,
            port=db_port,
            database=secrets['db_name']
        )
    )

    return engine



