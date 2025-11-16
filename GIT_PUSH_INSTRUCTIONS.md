# 🔐 GitHub Push - Authentication Fix

## ❌ Error
```
remote: Permission to tayyabriaz60/Deployment.git denied to Tayyriaz.
```

## ✅ Solution

### Option 1: GitHub Credentials Update (Recommended)

#### Windows Credential Manager se Purane Credentials Remove Karein:

1. **Windows Credential Manager** open karo:
   - Windows Key + R
   - Type: `control /name Microsoft.CredentialManager`
   - Enter press karo

2. **Windows Credentials** tab select karo

3. **github.com** search karo

4. Purane GitHub credentials **Remove** karo

5. Ab push command run karo - GitHub login prompt aayega

#### Ya PowerShell se:

```powershell
# GitHub credentials clear karo
git credential-manager-core erase
host=github.com
protocol=https
```

(Enter press karo 2 baar)

### Option 2: Personal Access Token Use Karein

1. **GitHub.com** par jao
2. **Settings** → **Developer settings** → **Personal access tokens** → **Tokens (classic)**
3. **Generate new token** click karo
4. **Note**: `Deployment Push Token`
5. **Expiration**: 90 days (ya custom)
6. **Scopes**: `repo` checkbox select karo
7. **Generate token** click karo
8. **Token copy karo** (sirf ek baar dikhega!)

9. Push command run karo:
```powershell
git push -u origin main
```

10. **Username**: `tayyabriaz60` enter karo
11. **Password**: Token paste karo (password ki jagah)

### Option 3: SSH Key Use Karein (Best for Long Term)

#### SSH Key Generate Karein:

```powershell
# SSH key check karo (agar hai to skip)
ssh-keygen -t ed25519 -C "your_email@example.com"

# Key copy karo
cat ~/.ssh/id_ed25519.pub
```

#### GitHub par SSH Key Add Karein:

1. GitHub.com → **Settings** → **SSH and GPG keys**
2. **New SSH key** click karo
3. **Title**: `Windows PC` (ya koi naam)
4. **Key**: Copy kiya hua key paste karo
5. **Add SSH key** click karo

#### Remote URL Change Karein:

```powershell
git remote set-url origin git@github.com:tayyabriaz60/Deployment.git
```

#### Push Karein:

```powershell
git push -u origin main
```

---

## 🚀 Quick Fix (Easiest)

### Step 1: Credentials Clear
```powershell
git credential-manager-core erase
host=github.com
protocol=https
```
(Enter 2 baar press karo)

### Step 2: Push Again
```powershell
git push -u origin main
```

### Step 3: Login Prompt
- **Username**: `tayyabriaz60` enter karo
- **Password**: GitHub password (ya Personal Access Token)

---

## ✅ Success!

Agar sab theek hai to ye dikhega:
```
Enumerating objects: ...
Writing objects: ...
To https://github.com/tayyabriaz60/Deployment.git
 * [new branch]      main -> main
Branch 'main' set up to track remote branch 'main' from 'origin'.
```

---

## 📝 Verify

GitHub.com par jao:
- https://github.com/tayyabriaz60/Deployment

Sab files dikhni chahiye!

