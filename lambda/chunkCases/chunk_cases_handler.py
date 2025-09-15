import boto3
import os
from langchain.document_loaders import JSONLoader
from langchain.vectorstores import OpenSearchVectorSearch
from opensearchpy import RequestsHttpConnection

def handler(event, context):
    s3 = boto3.client('s3')
    bucket = os.environ['RAW_CASES'] 
    vector_store_id = os.environ['VECTOR_STORE_ID']
    print("gets cases from :", bucket)
    print("chunks into: ", vector_store_id)
    
    rc = 200
    return {'status': rc}