# ArgoCD CI/CD Setup

GitOps deployment for the News Pipeline using ArgoCD.

---

## Prerequisites

- Kubernetes cluster (Minikube or cloud)
- kubectl configured
- Git repository with `k8s/` manifests

---

## Quick Setup

### 1. Install ArgoCD

```bash
# Create namespace
kubectl create namespace argocd

# Install ArgoCD
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Wait for ArgoCD to be ready
kubectl wait --for=condition=available deployment/argocd-server -n argocd --timeout=300s
```

### 2. Access ArgoCD UI

```bash
# Port-forward to access UI
kubectl port-forward svc/argocd-server -n argocd 8443:443

# Get initial admin password
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d
```

**Login**: https://localhost:8443 (admin / <password from above>)

### 3. Configure Repository

Before applying the Application:

1. Update `argocd/application.yaml` with your repository URL
2. If private repo, add credentials in ArgoCD UI → Settings → Repositories

### 4. Deploy Application

```bash
# Apply the ArgoCD Application
kubectl apply -f argocd/application.yaml

# Check sync status
kubectl get applications -n argocd
```

---

## Health Checks

The configuration includes custom health checks for:

| Resource        | Health Logic                                   |
| --------------- | ---------------------------------------------- |
| **Deployment**  | Ready replicas == desired replicas             |
| **StatefulSet** | All replicas ready                             |
| **Job**         | Succeeded > 0 = Healthy, Failed > 0 = Degraded |

---

## Sync Policy

| Setting       | Value      | Description                          |
| ------------- | ---------- | ------------------------------------ |
| **Auto Sync** | Enabled    | Automatically syncs when Git changes |
| **Self Heal** | Enabled    | Reverts manual changes               |
| **Prune**     | Enabled    | Deletes removed resources            |
| **Retry**     | 5 attempts | Retries on failure                   |

---

## Workflow

```
┌─────────────────────────────────────────────────────────┐
│                     GitOps Flow                         │
├─────────────────────────────────────────────────────────┤
│                                                         │
│   [Developer] → [Git Push] → [GitHub/GitLab]            │
│                                    ↓                    │
│                            [ArgoCD detects]             │
│                                    ↓                    │
│                            [Auto Sync]                  │
│                                    ↓                    │
│                            [K8s Apply]                  │
│                                    ↓                    │
│                            [Health Check]               │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## Troubleshooting

### Application not syncing

```bash
# Check application status
kubectl describe application news-pipeline -n argocd

# Force sync
argocd app sync news-pipeline --force
```

### View logs

```bash
kubectl logs -n argocd deployment/argocd-server
```

---

## File Structure

```
argocd/
├── application.yaml    # Main ArgoCD Application
└── README.md          # This file
```

---

**Last Updated**: 2025-12-31
