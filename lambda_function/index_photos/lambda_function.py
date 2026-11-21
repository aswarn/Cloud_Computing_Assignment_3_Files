
import json
import boto3
import urllib.parse

from opensearchpy import (
    OpenSearch,
    RequestsHttpConnection,
    AWSV4SignerAuth
)
s3 = boto3.client('s3')
rekognition = boto3.client('rekognition')

host = "search-photos-assignment3-ullwvnlsdzjfqnhkdzh7y5zeaq.us-east-1.es.amazonaws.com"
region = "us-east-1"

credentials = boto3.Session().get_credentials()

auth = AWSV4SignerAuth(credentials, region, 'es')

es = OpenSearch(
    hosts=[{'host': host, 'port': 443}],
    http_auth=auth,
    use_ssl=True,
    verify_certs=True,
    connection_class=RequestsHttpConnection
)


def lambda_handler(event, context):

    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(
            record["s3"]["object"]["key"]
        )
        response = s3.head_object(
            Bucket=bucket,
            Key=key
        )

        metadata = response.get("Metadata", {})
        raw_labels = metadata.get("customlabels", "")

        custom_labels = [
            label.strip()
            for label in raw_labels.split(",")
            if label.strip()
        ]

        rekog_response = rekognition.detect_labels(
            Image={
                'S3Object': {
                    'Bucket': bucket,
                    'Name': key
                }
            },
            MaxLabels=10
        )

        for label in rekog_response["Labels"]:
            custom_labels.append(label["Name"].lower())

        formatted_time = response["LastModified"].isoformat()

        json_obj = {
            "objectKey": key,
            "bucket": bucket,
            "createdTimestamp": formatted_time,
            "labels": custom_labels
        }

        print("Document to index:-", json_obj)

        es.index(
            index="photos",
            body=json_obj
        )

        print("Successfully indexed:", key)

    return {
        'statusCode': 200,
        'body': json.dumps('Photos indexed successfully!')
    }

