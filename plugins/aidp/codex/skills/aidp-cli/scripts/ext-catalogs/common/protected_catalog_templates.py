# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/
"""Unresolved templates for additional external catalog sources; no secret-file reads."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from protected_aidp import MAX_TEMPLATE, ProtectedError, read_file, write_body_template

TYPES = ("MYSQL", "DB2", "AZURE_SQLSERVER", "SNOWFLAKE", "GOOGLE_BIGQUERY",
         "SQLSERVER", "POSTGRESQL", "DATABRICKS_UNITY_CATALOG")


def text(config, name, required=True):
    value = config.get(name)
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip() or any(char in value for char in "\r\n{}"):
        raise ProtectedError("INVALID_CONFIG", "A required non-sensitive field is missing or invalid; check the source reference.")
    return value


def boolean(config, name):
    if name in config and type(config[name]) is not bool:
        raise ProtectedError("INVALID_CONFIG", "Boolean settings must be JSON true or false.")
    return config.get(name)


def prompt(label, hidden=True, required=True):
    return "{" + ("invisible" if hidden else "visible") + "_prompt_input:" + ("required" if required else "optional") + ":" + label + "}"


def template(source, operation, config):
    if source in ("SQLSERVER", "POSTGRESQL", "DATABRICKS_UNITY_CATALOG"):
        return connector_template(source, operation, config)
    if source == "GOOGLE_BIGQUERY":
        return google_bigquery_template(operation, config)
    common = {"host", "port", "databaseName", "sslEnabled", "workspaceKey"}
    create = {"displayName", "description", "properties"} if operation == "create" else set()
    snow = {"authenticationMethod", "warehouse", "role", "privateKeyFilePath", "privateKeyEncrypted"}
    allowed = common | create | {"catalogKey"} | (snow if source == "SNOWFLAKE" else set())
    if set(config) - allowed:
        raise ProtectedError("UNSUPPORTED_CONFIG", "Use only documented non-sensitive settings; credentials are prompted locally.")
    if source not in TYPES:
        raise ProtectedError("UNSUPPORTED_TYPE", "Select a supported catalog source.")
    if config.get("catalogKey") is not None:
        if operation != "test-connection":
            raise ProtectedError("INVALID_STORED_TEST", "catalogKey is only valid for a stored-catalog connection test.")
        expected = {"catalogKey", "authenticationMethod"} if source == "SNOWFLAKE" else {"catalogKey"}
        if set(config) - expected:
            raise ProtectedError("INVALID_STORED_TEST", "Stored-catalog password tests reuse existing metadata; supply only catalogKey and the verified Snowflake Basic authentication method when applicable.")
        if source == "SNOWFLAKE" and text(config, "authenticationMethod") != "Basic":
            raise ProtectedError("KEYPAIR_FULL_TEST_REQUIRED", "Snowflake KeyPair requires a full test without catalogKey; the stored shortcut replaces only passwords.")
        key = "password" if source == "DB2" else source + "_PASSWORD"
        return {"key": text(config, "catalogKey"), "sourceType": source,
                "connectionDetails": {"connectionProperties": {key: prompt("Enter replacement " + source + " password")}}}

    prefix = "" if source == "DB2" else source + "_"
    host, port = text(config, "host"), text(config, "port")
    if not port.isascii() or not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise ProtectedError("INVALID_PORT", "Port must be a string containing an actual listener port between 1 and 65535.")
    props = {prefix + ("HOST" if prefix else "host"): host,
             prefix + ("PORT" if prefix else "port"): port,
             prefix + ("USERNAME" if prefix else "user.name"): prompt("Enter " + source + " account username", hidden=False)}
    database = text(config, "databaseName", required=source != "MYSQL")
    if database is not None:
        props[prefix + ("DATABASE_NAME" if prefix else "database.name")] = database
    if source == "SNOWFLAKE":
        if "sslEnabled" in config:
            raise ProtectedError("UNSUPPORTED_CONFIG", "No Snowflake SSL-toggle property is established by this contract; do not invent one.")
        method = text(config, "authenticationMethod")
        if method not in ("Basic", "KeyPair"):
            raise ProtectedError("INVALID_AUTH_METHOD", "Select Snowflake authenticationMethod Basic or KeyPair.")
        props["SNOWFLAKE_AUTHENTICATION_METHOD"] = method
        props["SNOWFLAKE_WAREHOUSE"] = text(config, "warehouse")
        if "role" in config:
            props["SNOWFLAKE_ROLE"] = text(config, "role")
        if method == "KeyPair":
            path = text(config, "privateKeyFilePath")
            props["SNOWFLAKE_PRIVATE_KEY_CONTENT"] = "{textof:" + path + "}"
            encrypted = boolean(config, "privateKeyEncrypted")
            if encrypted is not False:
                props["SNOWFLAKE_PRIVATE_KEY_PASSPHRASE"] = prompt("Enter Snowflake private key passphrase", required=encrypted is True)
        elif "privateKeyFilePath" in config or "privateKeyEncrypted" in config:
            raise ProtectedError("INVALID_CONFIG", "Basic authentication does not use private-key settings.")
        else:
            props["SNOWFLAKE_PASSWORD"] = prompt("Enter Snowflake account password")
    else:
        props[prefix + ("PASSWORD" if prefix else "password")] = prompt("Enter " + source + " account password")
        if "sslEnabled" in config:
            props[prefix + ("SSL_ENABLED" if prefix else "ssl.enabled")] = str(boolean(config, "sslEnabled")).lower()
    if "workspaceKey" in config:
        props["WORKSPACE_KEY"] = text(config, "workspaceKey")
    body = {"sourceType": source, "connectionDetails": {"connectionProperties": props}}
    if operation == "create":
        body.update(displayName=text(config, "displayName"), catalogType="EXTERNAL")
        if "description" in config:
            if not isinstance(config["description"], str):
                raise ProtectedError("INVALID_CONFIG", "Description must be text.")
            body["description"] = config["description"]
        if "properties" in config:
            properties = config["properties"]
            if not isinstance(properties, dict) or any(not isinstance(value, str) for value in properties.values()):
                raise ProtectedError("INVALID_CONFIG", "Catalog properties must be a non-sensitive string-to-string object.")
            body["properties"] = properties
    return body


def connector_template(source, operation, config):
    """SQL Server/PostgreSQL password and Databricks OAuth M2M UI contracts."""
    if operation not in ("create", "test-connection"):
        raise ProtectedError("INVALID_OPERATION", "Select create or test-connection.")
    databricks = source == "DATABRICKS_UNITY_CATALOG"
    label = {"SQLSERVER": "SQL Server", "POSTGRESQL": "PostgreSQL",
             "DATABRICKS_UNITY_CATALOG": "Databricks"}[source]
    secret_key = source + ("_OAUTH_CLIENT_SECRET" if databricks else "_PASSWORD")
    secret_prompt = prompt("Enter " + label + (" OAuth client secret" if databricks else " account password"))
    if "catalogKey" in config:
        if operation != "test-connection" or set(config) != {"catalogKey"}:
            raise ProtectedError("INVALID_STORED_TEST", "An existing-catalog test takes only catalogKey and prompts locally for the replacement credential; it does not save it.")
        return {"key": text(config, "catalogKey"), "sourceType": source,
                "connectionDetails": {"connectionProperties": {secret_key: secret_prompt}}}

    public_fields = ({"workspaceUrl", "clientId", "remoteCatalog"} if databricks else
                     {"host", "port", "databaseName", "workspaceKey"})
    create_fields = {"displayName", "description", "properties", "isTestConnectionEnabled"} if operation == "create" else set()
    if set(config) - (public_fields | create_fields):
        raise ProtectedError("UNSUPPORTED_CONFIG", "Use only the selected source's public connection settings; credentials are entered privately at execution.")
    props = {secret_key: secret_prompt}
    if databricks:
        workspace_url = text(config, "workspaceUrl")
        try:
            parsed = urlsplit(workspace_url)
            valid = (parsed.scheme.lower() == "https" and parsed.hostname and not parsed.username
                     and not parsed.password and parsed.path in ("", "/")
                     and not parsed.query and not parsed.fragment and not any(c.isspace() for c in workspace_url))
            parsed.port  # Validate a supplied port without contacting the workspace.
        except ValueError:
            valid = False
        if not valid:
            raise ProtectedError("INVALID_WORKSPACE_URL", "Supply the HTTPS Databricks workspace base URL, without credentials, a query, or a path.")
        props.update(DATABRICKS_UNITY_CATALOG_WORKSPACE_URL=workspace_url,
                     DATABRICKS_UNITY_CATALOG_AUTH_TYPE="oauth-m2m",
                     DATABRICKS_UNITY_CATALOG_OAUTH_CLIENT_ID=text(config, "clientId"),
                     DATABRICKS_UNITY_CATALOG_REMOTE_CATALOG=text(config, "remoteCatalog"))
    else:
        # Only SQL Server has a reviewed UI default. PostgreSQL's port is required.
        port = text(config, "port") if "port" in config or source == "POSTGRESQL" else "1433"
        if not port.isascii() or not port.isdecimal() or not 1 <= int(port) <= 65535:
            raise ProtectedError("INVALID_PORT", "Supply a listener port between 1 and 65535 as a JSON string.")
        props.update({source + "_HOST": text(config, "host"), source + "_PORT": port,
                      source + "_USERNAME": prompt("Enter " + label + " account username", hidden=False)})
        database = text(config, "databaseName", required=source == "POSTGRESQL")
        if database is not None:
            props[source + "_DATABASE_NAME"] = database
        if "workspaceKey" in config:
            props["WORKSPACE_KEY"] = text(config, "workspaceKey")
    body = {"sourceType": source, "connectionDetails": {"connectionProperties": props}}
    if operation == "create":
        body.update(displayName=text(config, "displayName"), catalogType="EXTERNAL")
        if "description" in config:
            if not isinstance(config["description"], str):
                raise ProtectedError("INVALID_CONFIG", "Description must be text.")
            body["description"] = config["description"]
        if "properties" in config:
            properties = config["properties"]
            if not isinstance(properties, dict) or any(not isinstance(value, str) for value in properties.values()):
                raise ProtectedError("INVALID_CONFIG", "Catalog properties must be a public string-to-string object.")
            body["properties"] = properties
        if "isTestConnectionEnabled" in config:
            body["isTestConnectionEnabled"] = boolean(config, "isTestConnectionEnabled")
    return body


def google_bigquery_template(operation, config):
    """Service-account key content stays local until protected_aidp resolves it."""
    create = {"displayName", "description", "properties"} if operation == "create" else set()
    allowed = {"host", "port", "projectId", "serviceAccountEmail", "privateKeyFilePath", "workspaceKey", "catalogKey"} | create
    if set(config) - allowed:
        raise ProtectedError("UNSUPPORTED_CONFIG", "Use only documented public BigQuery fields and a local key-file path; do not include private key contents, passwords or access tokens.")
    path = text(config, "privateKeyFilePath")
    props = {"GOOGLE_BIGQUERY_OAUTH_PVT_KEY": "{textof:" + path + "}"}
    if "catalogKey" in config:
        if operation != "test-connection" or set(config) - {"catalogKey", "privateKeyFilePath"}:
            raise ProtectedError("INVALID_STORED_TEST", "A stored BigQuery test takes only catalogKey and the local replacement key-file path.")
        return {"key": text(config, "catalogKey"), "sourceType": "GOOGLE_BIGQUERY",
                "connectionDetails": {"connectionProperties": props}}
    port = text(config, "port")
    if not port.isascii() or not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise ProtectedError("INVALID_PORT", "Port must be a string containing an actual listener port between 1 and 65535.")
    props.update(GOOGLE_BIGQUERY_HOST=text(config, "host"), GOOGLE_BIGQUERY_PORT=port,
                 GOOGLE_BIGQUERY_PROJECT_ID=text(config, "projectId"),
                 GOOGLE_BIGQUERY_OAUTH_SERVICE_ACCT_EMAIL=text(config, "serviceAccountEmail"),
                 GOOGLE_BIGQUERY_OAUTH_TYPE="service_account")
    if "workspaceKey" in config:
        props["WORKSPACE_KEY"] = text(config, "workspaceKey")
    body = {"sourceType": "GOOGLE_BIGQUERY", "connectionDetails": {"connectionProperties": props}}
    if operation == "create":
        body.update(displayName=text(config, "displayName"), catalogType="EXTERNAL")
        if "description" in config:
            if not isinstance(config["description"], str):
                raise ProtectedError("INVALID_CONFIG", "Description must be text.")
            body["description"] = config["description"]
        if "properties" in config:
            if not isinstance(config["properties"], dict) or any(not isinstance(value, str) for value in config["properties"].values()):
                raise ProtectedError("INVALID_CONFIG", "Catalog properties must be a non-sensitive string-to-string object.")
            body["properties"] = config["properties"]
    return body


def main(source, argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operation", choices=("create", "test-connection"), required=True)
    parser.add_argument("--config", required=True, help="Non-sensitive JSON config, optionally prefixed by @")
    parser.add_argument("--output", required=True, help="Fresh unresolved body-template filename")
    args = parser.parse_args(argv)
    try:
        config = json.loads(read_file(args.config.removeprefix("@"), MAX_TEMPLATE))
        if not isinstance(config, dict):
            raise ProtectedError("INVALID_CONFIG", "Configuration must be a non-sensitive JSON object.")
        body = template(source, args.operation, config)
        write_body_template(args.output, body)
        print(json.dumps({"ok": True, "templateFile": args.output}))
        return 0
    except ProtectedError as error:
        print(json.dumps({"ok": False, "errorCode": error.code, "error": str(error)}))
    except FileExistsError:
        print('{"ok":false,"errorCode":"OUTPUT_EXISTS","error":"Choose a fresh template filename; existing files are never overwritten."}')
    except Exception:
        print('{"ok":false,"errorCode":"TEMPLATE_FAILED","error":"Could not prepare the template; input excerpts are suppressed."}')
    return 1
