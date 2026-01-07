# Security Hardening Guide for News Pipeline

## Overview
Security configurations for production deployment of the news pipeline.

---

## 1. Kubernetes Secrets

### Create Secrets for Sensitive Data
```bash
# Create namespace first
kubectl create namespace news-pipeline

# MongoDB credentials
kubectl create secret generic mongodb-credentials \
  --from-literal=username=newsadmin \
  --from-literal=password=$(openssl rand -base64 32) \
  -n news-pipeline

# Kafka credentials (for SASL)
kubectl create secret generic kafka-credentials \
  --from-literal=username=kafkauser \
  --from-literal=password=$(openssl rand -base64 32) \
  -n news-pipeline

# Airflow admin credentials
kubectl create secret generic airflow-credentials \
  --from-literal=username=admin \
  --from-literal=password=$(openssl rand -base64 24) \
  --from-literal=fernet-key=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())") \
  -n news-pipeline

# Schema Registry credentials
kubectl create secret generic schema-registry-credentials \
  --from-literal=api-key=$(openssl rand -hex 16) \
  --from-literal=api-secret=$(openssl rand -base64 32) \
  -n news-pipeline
```

### Reference Secrets in Deployments
```yaml
# Example: MongoDB deployment with secrets
containers:
- name: mongodb
  env:
  - name: MONGO_INITDB_ROOT_USERNAME
    valueFrom:
      secretKeyRef:
        name: mongodb-credentials
        key: username
  - name: MONGO_INITDB_ROOT_PASSWORD
    valueFrom:
      secretKeyRef:
        name: mongodb-credentials
        key: password
```

---

## 2. TLS Configuration

### Generate TLS Certificates
```bash
# Create CA
openssl genrsa -out ca-key.pem 4096
openssl req -new -x509 -days 365 -key ca-key.pem -out ca-cert.pem \
  -subj "/CN=news-pipeline-ca"

# Create Kafka server certificate
openssl genrsa -out kafka-key.pem 2048
openssl req -new -key kafka-key.pem -out kafka-csr.pem \
  -subj "/CN=kafka-broker.news-pipeline.svc.cluster.local"
openssl x509 -req -in kafka-csr.pem -CA ca-cert.pem -CAkey ca-key.pem \
  -CAcreateserial -out kafka-cert.pem -days 365

# Create MongoDB server certificate
openssl genrsa -out mongodb-key.pem 2048
openssl req -new -key mongodb-key.pem -out mongodb-csr.pem \
  -subj "/CN=mongodb.news-pipeline.svc.cluster.local"
openssl x509 -req -in mongodb-csr.pem -CA ca-cert.pem -CAkey ca-key.pem \
  -CAcreateserial -out mongodb-cert.pem -days 365
```

### Create TLS Secrets
```bash
# Kafka TLS secret
kubectl create secret tls kafka-tls \
  --cert=kafka-cert.pem \
  --key=kafka-key.pem \
  -n news-pipeline

# MongoDB TLS secret
kubectl create secret tls mongodb-tls \
  --cert=mongodb-cert.pem \
  --key=mongodb-key.pem \
  -n news-pipeline

# CA certificate for clients
kubectl create secret generic ca-certificate \
  --from-file=ca.crt=ca-cert.pem \
  -n news-pipeline
```

---

## 3. Kafka Security Configuration

### SASL/SSL Configuration (01-kafka-secure.yaml)
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: kafka-security-config
  namespace: news-pipeline
data:
  server.properties: |
    # Security protocol
    security.inter.broker.protocol=SASL_SSL
    ssl.truststore.location=/etc/kafka/secrets/truststore.jks
    ssl.truststore.password=${TRUSTSTORE_PASSWORD}
    ssl.keystore.location=/etc/kafka/secrets/keystore.jks
    ssl.keystore.password=${KEYSTORE_PASSWORD}
    
    # SASL configuration
    sasl.mechanism.inter.broker.protocol=PLAIN
    sasl.enabled.mechanisms=PLAIN
    
    # Listener security
    listener.security.protocol.map=INTERNAL:SASL_SSL,EXTERNAL:SASL_SSL
    
    # Authorization
    authorizer.class.name=kafka.security.authorizer.AclAuthorizer
    super.users=User:admin
```

---

## 4. MongoDB Security Configuration

### Enable Authentication
```yaml
# MongoDB with authentication
containers:
- name: mongodb
  image: mongo:7.0
  args:
  - "--auth"
  - "--tlsMode=requireTLS"
  - "--tlsCertificateKeyFile=/etc/mongodb/tls/mongodb.pem"
  - "--tlsCAFile=/etc/mongodb/tls/ca.crt"
  volumeMounts:
  - name: tls-certs
    mountPath: /etc/mongodb/tls
    readOnly: true
volumes:
- name: tls-certs
  secret:
    secretName: mongodb-tls
```

---

## 5. Network Policies

### Restrict Pod-to-Pod Communication
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: news-pipeline-network-policy
  namespace: news-pipeline
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  - Egress
  ingress:
  # Allow internal namespace traffic
  - from:
    - namespaceSelector:
        matchLabels:
          name: news-pipeline
  egress:
  # Allow internal namespace traffic
  - to:
    - namespaceSelector:
        matchLabels:
          name: news-pipeline
  # Allow DNS
  - to:
    - namespaceSelector: {}
    ports:
    - protocol: UDP
      port: 53
```

### Kafka-specific Network Policy
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: kafka-network-policy
  namespace: news-pipeline
spec:
  podSelector:
    matchLabels:
      app: kafka
  policyTypes:
  - Ingress
  ingress:
  # Allow only from crawler, spark, schema-registry
  - from:
    - podSelector:
        matchLabels:
          app: crawler
    - podSelector:
        matchLabels:
          app: spark-master
    - podSelector:
        matchLabels:
          app: spark-worker
    - podSelector:
        matchLabels:
          app: sr
    ports:
    - protocol: TCP
      port: 9092
```

---

## 6. Secret Rotation Policy

### Automated Secret Rotation Script
```bash
#!/bin/bash
# secret_rotation.sh - Run monthly via cron

NAMESPACE="news-pipeline"

# Rotate MongoDB password
NEW_MONGO_PASS=$(openssl rand -base64 32)
kubectl create secret generic mongodb-credentials \
  --from-literal=username=newsadmin \
  --from-literal=password=$NEW_MONGO_PASS \
  -n $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -

# Rotate Kafka credentials
NEW_KAFKA_PASS=$(openssl rand -base64 32)
kubectl create secret generic kafka-credentials \
  --from-literal=username=kafkauser \
  --from-literal=password=$NEW_KAFKA_PASS \
  -n $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -

# Restart deployments to pick up new secrets
kubectl rollout restart deployment/mongodb -n $NAMESPACE
kubectl rollout restart deployment/kafka -n $NAMESPACE
kubectl rollout restart deployment/crawler -n $NAMESPACE

echo "Secrets rotated at $(date)"
```

### Kubernetes CronJob for Rotation
```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: secret-rotation
  namespace: news-pipeline
spec:
  schedule: "0 0 1 * *"  # First day of each month
  jobTemplate:
    spec:
      template:
        spec:
          serviceAccountName: secret-rotation-sa
          containers:
          - name: rotate-secrets
            image: bitnami/kubectl:latest
            command: ["/bin/sh", "-c"]
            args:
            - |
              # Rotation logic here
              echo "Rotating secrets..."
          restartPolicy: OnFailure
```

---

## 7. RBAC Configuration

### Service Account with Minimal Permissions
```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: news-pipeline-sa
  namespace: news-pipeline
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: news-pipeline-role
  namespace: news-pipeline
rules:
- apiGroups: [""]
  resources: ["pods", "services", "configmaps"]
  verbs: ["get", "list", "watch"]
- apiGroups: [""]
  resources: ["secrets"]
  verbs: ["get"]  # Read-only for secrets
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: news-pipeline-binding
  namespace: news-pipeline
subjects:
- kind: ServiceAccount
  name: news-pipeline-sa
roleRef:
  kind: Role
  name: news-pipeline-role
  apiGroup: rbac.authorization.k8s.io
```

---

## 8. Security Checklist

| Category | Item | Status |
|----------|------|--------|
| **Secrets** | Use K8s Secrets for credentials | ☐ |
| **Secrets** | Avoid hardcoded passwords | ☐ |
| **Secrets** | Implement secret rotation | ☐ |
| **TLS** | Enable TLS for Kafka | ☐ |
| **TLS** | Enable TLS for MongoDB | ☐ |
| **TLS** | Use cert-manager for auto-renewal | ☐ |
| **Network** | Implement NetworkPolicies | ☐ |
| **Network** | Restrict egress to necessary endpoints | ☐ |
| **RBAC** | Use ServiceAccounts | ☐ |
| **RBAC** | Apply least-privilege principle | ☐ |
| **Audit** | Enable Kubernetes audit logs | ☐ |
| **Scanning** | Scan container images for CVEs | ☐ |

---

## Notes

- **Development**: Current manifests use default credentials for ease of setup
- **Production**: Apply all security configurations before deployment
- **Compliance**: Consider GDPR/CCPA requirements for news data
