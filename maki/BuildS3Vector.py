"""
MAKI OpenSearch Serverless Components Builder

This module creates S3 Vector infrastructure for MAKI's events processing
mode, providing vector search capabilities and scalable event storage.

Purpose:
- Create S3 Vector Bucket and index for health events storage
- Configure security policies for encryption, network access, and data access
- Enable vector search capabilities for semantic analysis
- Provide dashboard access for data exploration and monitoring

Components Created:
- S3 Vector Bucket and vector index with search optimization
- Encryption policy using AWS-owned keys
- Network policy allowing public access (secured by data access policy)
- Data access policy with least-privilege permissions
- IAM policies for dashboard access and collection management

Key Features:
- S3 Vector Bucket and Index 
- Vector search support for semantic similarity using Cosine similarity
- Comprehensive security policy configuration
- Integration with MAKI execution role and current user
- Dashboard access for data visualization and debugging

Security Configuration:
- Encryption at rest using AWS-owned keys
- Network access controlled through security policies
- Data access restricted to MAKI execution role and deploying user
- Separate permissions for collection operations and index management

Usage:
- Deployed by MakiEmbeddings stack for health events mode
- Stores health events with vector embeddings for semantic search
- Provides scalable storage for large volumes of health data
- Enables advanced querying and similarity search capabilities
"""

import aws_cdk as cdk
import aws_cdk.aws_iam as iam
import aws_cdk.custom_resources as cr
import cdk_s3_vectors as s3vectors
import config
import sys
sys.path.append('utils')
import utils

def buildS3Vector(self, execution_role):
    #   S3Vector is still in preview and doesn't have many options.
    # Create S3 Vector bucket
    vector_bucket = config.S3_VECTOR_BUCKET_NAME
    vector_index = config.S3_VECTOR_INDEX_NAME

    s3vector_bucket = s3vectors.Bucket(self,
        id = vector_bucket,
        vector_bucket_name=vector_bucket
        )

    # Create S3 Vector index
    s3vector_index = s3vectors.Index(self,
        id = vector_index,
        vector_bucket_name=vector_bucket,
        index_name = vector_index,
        dimension = config.S3_VECTOR_INDEX_DIMENSION,
        data_type = 'float32',
        distance_metric = 'cosine',
        )

    return s3vector_bucket, s3vector_index
