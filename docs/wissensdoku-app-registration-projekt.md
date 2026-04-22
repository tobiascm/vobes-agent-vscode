# Wissensdokumentation App Registration fuer dieses Projekt

Stand: 2026-04-21

## Ziel

Diese Dokumentation fasst die aktuell gelesenen Inhalte aus dem Global Tenant Infoboard zusammen, damit fuer dieses Projekt eine spaetere App Registration strukturiert, vollstaendig und governance-konform vorbereitet werden kann.

## Ausgewertete Quellen

- Allgemeine Informationen zur App Registration:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Dokumentation-App-Registration.aspx](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Dokumentation-App-Registration.aspx)
- App Registration Antrag:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Antrag-Request--App-Registration.aspx](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Antrag-Request--App-Registration.aspx)
- API-Zugriff auf ein Exchange Online Postfach:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/API-Zugriff-auf-ein-Exchange-Online-Postfach.aspx](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/API-Zugriff-auf-ein-Exchange-Online-Postfach.aspx)
- FAQs App Registration:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/FAQ--App-Registration.aspx](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/FAQ--App-Registration.aspx)

## Konsolidierte Kernaussagen

### 1) Grundsaetzliches zur App Registration

- App Registration stellt die Vertrauensbeziehung zwischen Anwendung und Microsoft Identity Platform/Entra ID her.
- Eine reine Standard-Registrierung prueft primaer gueltige Identitaeten; der eigentliche Nutzen entsteht durch korrekte Konfiguration von Redirect URIs, Secrets/Zertifikaten und API Permissions.
- Unterscheidung der Berechtigungen:
  - Delegated Permissions: Zugriff im Kontext eines angemeldeten Benutzers.
  - Application Permissions: Zugriff im Kontext der Anwendung (Daemon/Service), in der Regel mit Admin Consent.

### 2) Relevanz fuer dieses Projekt

- Fuer einen lokalen Agenten ohne manuelles Browser-Token-Abfischen ist der vorgesehene Weg:
  - App Registration
  - Moderne Authentifizierung
  - Client Credential Flow (Secret oder bevorzugt Zertifikat)
  - Microsoft Graph API
- Fuer Mail-Szenarien ist der Prozess explizit beschrieben und tragfaehig.
- Fuer Teams-Szenarien wird der Freigabeprozess ueber Teams Service Owner/Governance adressiert, nicht als inoffizieller SPA-Token-Workaround.

### 3) Exchange Online API Zugriff (Funktionspostfach)

- Zugriff erfolgt via Modern Auth und Graph, Basic Auth (SMTP/IMAP/POP3) ist nicht vorgesehen.
- Fokus liegt auf nicht-personenbezogenen Postfaechern (z. B. Shared Mailbox).
- Mögliche Graph Application Permissions fuer mailbox-spezifische Freigabe laut Seite:
  - Mail.Read
  - Mail.ReadBasic
  - Mail.ReadBasic.All
  - Mail.ReadWrite
  - Mail.Send
  - MailboxSettings.Read
  - MailboxSettings.ReadWrite
  - Calendars.Read
  - Calendars.ReadWrite
  - Contacts.Read
  - Contacts.ReadWrite
- Einschraenkung auf konkrete Postfaecher erfolgt tenantseitig per Application Access Policy.
- Technisches Testmuster auf der Seite:
  - OAuth2 Client Credentials gegen `https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token`
  - `scope=https://graph.microsoft.com/.default`
  - Graph-Aufrufbeispiel fuer Mailversand via `POST /v1.0/users/{MailboxID}/sendMail`
  - Hinweis aus dem Beispiel: MailboxID entspricht UPN/E-Mailadresse.
- Netzwerkhinweis aus dem Beispiel:
  - Proxy-Nutzung im Skript ist vorgesehen (Systemproxy / `-ProxyUseDefaultCredentials`).
- Rollen-/Testhinweis:
  - Fuer Konfiguration im DEV wird ein Admin-Account benoetigt.
  - Tests muessen mit normalem Test-Benutzeraccount erfolgen, da Admin-Accounts kein Postfach besitzen duerfen.

### 4) Prozess- und Governance-Anforderungen

- Dev zuerst, Prod danach.
- Konfiguration und Tests erfolgen im Dev Tenant.
- 1:1 Ueberfuehrung in Prod durch GTA nach Freigaben.
- LeanIX/ICTO/IT-Sicherheits- und Datenschutzkontext muss vorhanden sein.
- Testuser und Lizenzthemen pro Stufe (Dev/QA/Prod) muessen eingeplant werden.
- Internetzugang ueber VW-Proxy und lokale Security-Vorgaben sind Voraussetzung.
- Lifecycle ist verpflichtend: jaehrlicher Review, sonst Deaktivierung und anschliessend Loeschung moeglich.

### 5) Rollen und Verantwortungen

- GTA verantwortet zentrale Tenant-Umsetzung und Ueberfuehrung nach Prod.
- Projekt/Antragsteller verantwortet:
  - Anforderungen und Spezifikation
  - technische Konfiguration im Dev
  - realitaetsnahe Tests
  - Bereitstellung der erforderlichen Nachweise und Dokumente
- Bei Teams-Apps erfolgt Freigabekette ueber den Service Owner Teams.

### 6) Prozess App Registration (neu eingearbeitet)

- Die Prozessseite positioniert den App-Registration-Ablauf explizit als Ergaenzung zum IT-PEP, nicht als Ersatz.
- GTA soll fruehzeitig im App-Entstehungsprozess eingebunden werden, damit Berechtigungen, Rollen und technische Randbedingungen frueh geklaert sind.
- Nach Antragstellung wird automatisch ein Service Change in Azure DevOps erzeugt und gemaess O365-Changeprozess bearbeitet.
- Verantwortungsabgrenzung wird klar festgelegt:
  - Projektleiter/Anforderer: Anforderungen, Konfiguration im Dev, Tests, Nachweise/Freigaben, finale Abnahme und Go-Live.
  - GTA: technische Registrierung in Dev, Ueberfuehrung nach Prod (1:1) nach vollstaendigen Freigaben.
  - IT Security je Marke: Freigaben und Bewertung gemaess markenspezifischem Prozess.
- Zusaetzliche zentrale Voraussetzung fuer Prod-Umsetzung laut Prozessseite:
  - LeanIX-Eintrag mit hinterlegten Freigaben (Schnittstellenbeschreibung, IT-Security-Freigabe, Datenschutzbewertung).
  - Bei markenabhaengigen Pfaden ggf. zusaetzliche Gremien-/Security-Prozesse (z. B. AUDI Risikomanagement).
- Die Seite nennt konkrete Mindestinformationen fuer die Registrierung:
  - App-Name, Kontotypen, Zielgruppe, Ansprechpartner/Postfach
  - Lastenheft (falls vorhanden), Kurzbeschreibung
  - URL zu Nutzungsbedingungen/Datenschutz (insb. Teams Apps)
  - Supportstruktur (Servicestellen/SC3/Knowledge Records)
  - Schnittstellenbeschreibung, LeanIX ID
  - Nachweis zur Betriebsratsvorlage

### 7) Antragsformular (eingebettet auf der Antragsseite)

Hinweis: Der folgende Abschnitt basiert auf dem eingebetteten Formularinhalt, den du bereitgestellt hast.

#### Zentrale Hinweise im Formular

- Nur einen Antrag pro App stellen (gilt fuer alle Stages DEV/PROD).
- Fuer Aenderungen an vorhandenen App Registrations keinen neuen Antrag stellen.
- Aenderungen bestehender Apps ausschliesslich ueber SC3 Service Request beantragen.
- Formular nur fuer neue App Registrations / Enterprise Apps nutzen.

#### Formularfelder (aus dem eingebetteten Formular)

1. Name

- Name der Applikation (nicht der Personenname).

1. Verantwortlicher

- E-Mail der verantwortlichen Person.
- Diese Person wird im Prozess kontaktiert und ist Lifecycle-Ansprechpartner.
- Externe Mitarbeiter duerfen nicht als Verantwortliche hinterlegt werden.

1. Stellvertreter

- E-Mail eines oder mehrerer Stellvertreter.
- Mehrere Eintraege mit Semikolon trennen.

1. Kurzbeschreibung

- Beschreibung der Applikation.
- Begruendung, warum Zugriff auf Ressourcen im Azure Tenant benoetigt wird.

1. ICTO

- LeanIX-Referenz angeben.

1. Zielgruppe

- Wer darf sich ueber die App Registration authentifizieren (Service Principal, Systemuser, Gruppenmitglieder, etc.).

1. Supportstruktur

- Servicestellen, SC3 Gruppen, Knowledge Records.
- Hinweis: Applikationsverantwortlicher verantwortet Support, GTA richtet App ein.

1. IT Sicherheitsbewertung (optional)

- Falls vorhanden: Referenz angeben (z. B. ITSB Nummer).

1. Betriebsrat (optional)

- Nachweis ueber Vorlage der App beim Betriebsrat (z. B. bei Teams).

1. Applikations Typ

- Enterprise App
- App Registration
- Integrated App
- Teams App

#### Abgeleitete Projektregeln aus dem Formular

- Keine Doppelantraege je App erzeugen.
- Aenderungen immer ueber SC3 Service Request kanalisiert einsteuern.
- Verantwortliche und Stellvertreter frueh festlegen, da diese in Betrieb und Lifecycle zentral sind.
- Vor Absenden mindestens die Felder Name, Verantwortlicher, Kurzbeschreibung, ICTO, Zielgruppe und Supportstruktur finalisieren.

### 8) Zugriff auf eine Sharepoint Seite ueber eine App Registration (neu)

- Die Seite beschreibt den technischen Pfad, um einer registrierten App gezielten Zugriff auf eine SharePoint-Site zu geben.
- Empfohlene Berechtigung ist Sites.Selected (Least-Privilege-Ansatz fuer Site-begrenzte Freigabe).
- Alternativen werden genannt, falls Sites.Selected nicht genutzt wird:
  - Files.SelectedOperations.Selected
  - ListItems.SelectedOperations.Selected
  - Lists.SelectedOperations.Selected
- Fuer die konkrete Berechtigung der App auf die Site wird ein PowerShell-Ablauf vorgegeben:
  1. Modul installieren
  2. Connect durchfuehren
  3. Berechtigungen setzen
  4. Zugriff pruefen
- Organisatorische Voraussetzung laut Seite:
  - Der eingesetzte Adminuser (DA_/PA_) muss Websitesammlungsadministrator sein.
  - Pfad zur Pruefung in SharePoint: Websiteberechtigungen -> Erweiterte Berechtigungen -> Websitesammlungsadministratoren.
- Technische Voraussetzung laut Seite:
  - PowerShell Version >= 7 verwenden.

### 9) Admin User Antrag (neu)

- Fuer administrative Taetigkeiten in den Volkswagen Group Tenants ist ein Admin User erforderlich.
- Pro Umgebung wird ein separater Admin User benoetigt (z. B. DEV-Admin fuer DEV-Tenant).
- Rollenzuweisungen erfolgen ueber Privileged Identity Management (PIM).
- Voraussetzung fuer Adminrechte:
  - Pflichtteilnahme an der webbasierten Schulung "IT-Sicherheit fuer Administratoren".
  - Nachweis wird in VCD dokumentiert und ist auf 2 Jahre befristet.
  - Bei fehlender/abgelaufener Teilnahmebestaetigung wird das Administratorkonto deaktiviert.
- Beantragung erfolgt ueber MyServe (Microsoft 365: Entra Admin User).
- Fuer Betriebsfaelle existieren zusaetzliche SC3-Ticket-Vorlagen (MFA Reset, Passwort Reset, Loeschung).

## Konkrete Projekt-Checkliste fuer spaetere Beantragung

### A) Vor dem Antrag

- Fachliche Zielarchitektur final festlegen:
  - Welche APIs genau?
  - Delegated vs Application je Endpunkt?
  - Welche Datenobjekte werden gelesen/geschrieben?
- Dokumentation vorbereiten:
  - LeanIX/ICTO Referenz
  - Schnittstellenbeschreibung
  - IT-Sicherheitsbewertung
  - Datenschutzbewertung
  - Betriebs- und Berechtigungskonzept
- Entscheiden:
  - Secret vs Zertifikat (empfohlen Zertifikat)
  - Benoetigte Umgebungen (Dev/QA/Prod)
  - Testuser und Lizenzen

### B) Bei der Beantragung

- Request App Registration vollstaendig ausfuellen.
- API Permissions frueh final abstimmen, um spaetere Security-Rework-Schleifen zu vermeiden.
- Falls Application Permissions noetig sind: Admin-Consent- und Policy-Pfad direkt mitdenken.

### C) Nach Anlage im Dev

- Konfiguration vollstaendig durchfuehren:
  - Authentication
  - Redirect URIs
  - Certificates/Secrets
  - API Permissions
  - Token-Konfiguration
- E2E-Tests gegen projektnahe Use Cases.
- Nachweis der Tests und Freigaben fuer Prod vorbereiten.

### D) Ueberfuehrung nach Prod

- GTA zur Uebernahme informieren.
- Ggf. IT-SEC-Gremiumstermin wahrnehmen, insbesondere bei relevanten Berechtigungs-/Sicherheitsaenderungen.
- Nach Prod-Rollout Betriebs- und Lifecycle-Verantwortung aktiv halten.

## Einschraenkungen und Hinweise fuer dieses Projekt

- Die eingebetteten Forms-Komponenten der Antragsseiten waren in der Bridge teilweise mit 401 nicht vollstaendig auslesbar.
- Die hier dokumentierten Inhalte basieren auf den sichtbaren Seiteninhalten inkl. ausgeklappter FAQ und verlinkter Fachseiten.

## Vollstaendige Linksammlung aus den gelesenen Seiten

### Hauptseiten

- Global Tenant Infoboard:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard)
- Doku App Registration:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Dokumentation-App-Registration.aspx](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Dokumentation-App-Registration.aspx)
- FAQ App Registration:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/FAQ--App-Registration.aspx](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/FAQ--App-Registration.aspx)
- Antrag App Registration:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Antrag-Request--App-Registration.aspx](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Antrag-Request--App-Registration.aspx)
- Prozess App Registration:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Prozess-App-Registration.aspx](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Prozess-App-Registration.aspx)

### Prozessseite App Registration (neu)

- App Entstehungsprozess:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Prozess-App-Registration.aspx#app-entstehungsprozess](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Prozess-App-Registration.aspx#app-entstehungsprozess)
- Abgrenzung Verantwortlichkeiten:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Prozess-App-Registration.aspx#abgrenzung-der-verantwortlichkeiten](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Prozess-App-Registration.aspx#abgrenzung-der-verantwortlichkeiten)
- Beantragungs- und Implementierungsprozess:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Prozess-App-Registration.aspx#beantragungs-und-implementierungsprozess-app-registration](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Prozess-App-Registration.aspx#beantragungs-und-implementierungsprozess-app-registration)
- Konfiguration im Volkswagen Group Dev Tenant:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Prozess-App-Registration.aspx#konfiguration-einer-app-registration-im-volkswagen-group-dev-tenant](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Prozess-App-Registration.aspx#konfiguration-einer-app-registration-im-volkswagen-group-dev-tenant)
- Prozessablauf:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Prozess-App-Registration.aspx#prozessablauf](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Prozess-App-Registration.aspx#prozessablauf)
- Prozessueberblick App Entstehungsprozess:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Prozess-App-Registration.aspx#prozess%C3%BCberblick-app-entstehungsprozess](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Prozess-App-Registration.aspx#prozess%C3%BCberblick-app-entstehungsprozess)

### Exchange und Mail-bezogene Seite

- API Zugriff Exchange Online Postfach:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/API-Zugriff-auf-ein-Exchange-Online-Postfach.aspx](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/API-Zugriff-auf-ein-Exchange-Online-Postfach.aspx)
- Anchor Zugriff Funktionspostfach:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/API-Zugriff-auf-ein-Exchange-Online-Postfach.aspx#wie-erfolgt-der-zugriff-auf-das-funktionspostfach](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/API-Zugriff-auf-ein-Exchange-Online-Postfach.aspx#wie-erfolgt-der-zugriff-auf-das-funktionspostfach)
- Anchor Berechtigungen:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/API-Zugriff-auf-ein-Exchange-Online-Postfach.aspx#welche-anwendungsberechtigungen-auf-ein-exchange-online-funktionspostfach-gibt-es](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/API-Zugriff-auf-ein-Exchange-Online-Postfach.aspx#welche-anwendungsberechtigungen-auf-ein-exchange-online-funktionspostfach-gibt-es)
- Anchor Voraussetzungen:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/API-Zugriff-auf-ein-Exchange-Online-Postfach.aspx#welche-voraussetzungen-m%C3%BCssen-im-vorfeld-sichergestellt-werden](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/API-Zugriff-auf-ein-Exchange-Online-Postfach.aspx#welche-voraussetzungen-m%C3%BCssen-im-vorfeld-sichergestellt-werden)
- Anchor Schritte:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/API-Zugriff-auf-ein-Exchange-Online-Postfach.aspx#welche-schritte-sind-f%C3%BCr-die-einrichtung-des-api-zugriffs-auf-ein-funktionspostfach-notwendig](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/API-Zugriff-auf-ein-Exchange-Online-Postfach.aspx#welche-schritte-sind-f%C3%BCr-die-einrichtung-des-api-zugriffs-auf-ein-funktionspostfach-notwendig)

### App Registration Detail-Anchor

- Was ist eine App Registration:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Dokumentation-App-Registration.aspx#was-ist-eine-app-registration](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Dokumentation-App-Registration.aspx#was-ist-eine-app-registration)
- Einteilung der Applikationen:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Dokumentation-App-Registration.aspx#einteilung-der-applikationen-f%C3%BCr-die-app-registration](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Dokumentation-App-Registration.aspx#einteilung-der-applikationen-f%C3%BCr-die-app-registration)
- Teams Apps:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Dokumentation-App-Registration.aspx#teams-apps](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Dokumentation-App-Registration.aspx#teams-apps)
- Grundlagen App Registrierung:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Dokumentation-App-Registration.aspx#grundlagen-zur-app-registrierung](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Dokumentation-App-Registration.aspx#grundlagen-zur-app-registrierung)
- Azure Portal und Identity Plattform:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Dokumentation-App-Registration.aspx#azure-portal-und-microsoft-identity-plattform](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Dokumentation-App-Registration.aspx#azure-portal-und-microsoft-identity-plattform)
- Anwendungs-ID:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Dokumentation-App-Registration.aspx#anwendungs-id-(client-id)](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Dokumentation-App-Registration.aspx#anwendungs-id-(client-id))
- Zugriffstoken:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Dokumentation-App-Registration.aspx#zugrifftoken](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Dokumentation-App-Registration.aspx#zugrifftoken)
- ID-Token:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Dokumentation-App-Registration.aspx#id-token](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Dokumentation-App-Registration.aspx#id-token)
- Umleitungs-URIs:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Dokumentation-App-Registration.aspx#umleitungs-uris](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Dokumentation-App-Registration.aspx#umleitungs-uris)
- Zertifikate und Geheimnisse:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Dokumentation-App-Registration.aspx#zertifikate-clientgeheimnisse](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Dokumentation-App-Registration.aspx#zertifikate-clientgeheimnisse)
- API Permissions:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Dokumentation-App-Registration.aspx#api-berechtigungen-(api-permissions)](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Dokumentation-App-Registration.aspx#api-berechtigungen-(api-permissions))

### Formulare und weiterfuehrende Tenant-Links

- SPO App Antrag:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/SPO-App-Request.aspx](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/SPO-App-Request.aspx)
- Zugriff SharePoint Seite ueber App Registration:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Zugriff-auf-eine-Sharepoint-Seite-über-eine-App-Registration.aspx](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Zugriff-auf-eine-Sharepoint-Seite-über-eine-App-Registration.aspx)
- Test User DEV:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Beantragung-von-Test-Users---DEV-Umgebung.aspx](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Beantragung-von-Test-Users---DEV-Umgebung.aspx)
- Admin User Antrag Formular:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Admin%20User%20Antrag%20Formular.aspx](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Admin%20User%20Antrag%20Formular.aspx)
- App Reg Sprechstunde:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/App-Reg-Sprechstunde.aspx](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/App-Reg-Sprechstunde.aspx)

### Admin User Antrag und Betrieb (neu)

- Admin User Antrag Seite:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Admin%20User%20Antrag%20Formular.aspx](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Admin%20User%20Antrag%20Formular.aspx)
- PIM Seite:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/PIM.aspx](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/PIM.aspx)
- FAQ Entra Admin User:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/FAQ---Entra-Admin-User.aspx](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/FAQ---Entra-Admin-User.aspx)
- Azure AD Rollen Seite:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Azure-AD-Rollen.aspx](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Azure-AD-Rollen.aspx)
- MyServe Antrag Microsoft 365: Entra Admin User:  
[https://myserveprod.service-now.com/myserve?id=sc_cat_item&table=sc_cat_item&sys_id=829ff6cb9358e2d08e88345efaba10d7](https://myserveprod.service-now.com/myserve?id=sc_cat_item&table=sc_cat_item&sys_id=829ff6cb9358e2d08e88345efaba10d7)
- SC3 Template Admin User MFA Reset:  
[https://myserveprod.service-now.com/myserve?id=template_detail&table=u_sc_ticket_mockup&sys_id=-1&sysparm_templateID=d49f0a9fffae595095b149ae435b5edf](https://myserveprod.service-now.com/myserve?id=template_detail&table=u_sc_ticket_mockup&sys_id=-1&sysparm_templateID=d49f0a9fffae595095b149ae435b5edf)
- SC3 Template Admin User Passwort Reset:  
[https://myserveprod.service-now.com/myserve?id=template_detail&table=u_sc_ticket_mockup&sys_id=-1&sysparm_templateID=c5cdad9bff62d95095b1eede435b5e8a](https://myserveprod.service-now.com/myserve?id=template_detail&table=u_sc_ticket_mockup&sys_id=-1&sysparm_templateID=c5cdad9bff62d95095b1eede435b5e8a)
- SC3 Template Admin User Loeschung:  
[https://myserveprod.service-now.com/myserve?id=template_detail&table=u_sc_ticket_mockup&sys_id=-1&sysparm_templateID=adb756dbffee595095b149ae435b5e92](https://myserveprod.service-now.com/myserve?id=template_detail&table=u_sc_ticket_mockup&sys_id=-1&sysparm_templateID=adb756dbffee595095b149ae435b5e92)

### SharePoint Site Zugriff via App Registration (neu)

- Hauptseite:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Zugriff-auf-eine-Sharepoint-Seite-%C3%BCber-eine-App-Registration.aspx](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Zugriff-auf-eine-Sharepoint-Seite-%C3%BCber-eine-App-Registration.aspx)
- Anchor Erlaubte Application API Permissions:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Zugriff-auf-eine-Sharepoint-Seite-%C3%BCber-eine-App-Registration.aspx#erlaubte-application-api-permissions](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Zugriff-auf-eine-Sharepoint-Seite-%C3%BCber-eine-App-Registration.aspx#erlaubte-application-api-permissions)
- Anchor Einrichtung Zugriff der App auf die Site:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Zugriff-auf-eine-Sharepoint-Seite-%C3%BCber-eine-App-Registration.aspx#einrichtung-des-zugriffs-der-app-auf-die-site](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Zugriff-auf-eine-Sharepoint-Seite-%C3%BCber-eine-App-Registration.aspx#einrichtung-des-zugriffs-der-app-auf-die-site)
- Anchor PowerShell 7 installieren:  
[https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Zugriff-auf-eine-Sharepoint-Seite-%C3%BCber-eine-App-Registration.aspx#powershell-7-installieren](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/Zugriff-auf-eine-Sharepoint-Seite-%C3%BCber-eine-App-Registration.aspx#powershell-7-installieren)

### Externe Referenzen aus den Seiten

- IT-AGP Authentication Solutions:  
[https://group-wiki.wob.vw.vwg/wikis/display/ITAPF/Authentication+Solutions#AuthenticationSolutions-EntraID%28AzureAD%29](https://group-wiki.wob.vw.vwg/wikis/display/ITAPF/Authentication+Solutions#AuthenticationSolutions-EntraID%28AzureAD%29)
- IT-PEP Volkswagen:  
[https://volkswagen-net.de/wikis/display/ITPEP](https://volkswagen-net.de/wikis/display/ITPEP)
- IT-PEP Audi:  
[https://volkswagengroup.sharepoint.com/sites/IT-PEPAudi](https://volkswagengroup.sharepoint.com/sites/IT-PEPAudi)
- AUDI IT-Security-Risikomanagementprozess:  
[https://volkswagengroup.sharepoint.com/sites/AudiMynet-ITSecurity/SitePages/IT-Security-Risikomanagementprozess.aspx](https://volkswagengroup.sharepoint.com/sites/AudiMynet-ITSecurity/SitePages/IT-Security-Risikomanagementprozess.aspx)
- WBT IT-Sicherheit fuer Administratoren:  
[https://wbt.wob.vw.vwg/wbtadmin/](https://wbt.wob.vw.vwg/wbtadmin/)
- PowerShell 7 Installation (Microsoft Learn):  
[https://learn.microsoft.com/de-de/powershell/scripting/install/install-powershell-on-windows](https://learn.microsoft.com/de-de/powershell/scripting/install/install-powershell-on-windows)
- MyAccess:  
[https://myaccess.microsoft.com/](https://myaccess.microsoft.com/)
- Microsoft Permissions und Consent:  
[https://docs.microsoft.com/en-us/azure/active-directory/develop/v2-permissions-and-consent#permission-types](https://docs.microsoft.com/en-us/azure/active-directory/develop/v2-permissions-and-consent#permission-types)
- OAuth2 Client Credentials:  
[https://docs.microsoft.com/en-us/azure/active-directory/develop/v2-oauth2-client-creds-grant-flow](https://docs.microsoft.com/en-us/azure/active-directory/develop/v2-oauth2-client-creds-grant-flow)
- EWS OAuth:  
[https://docs.microsoft.com/en-us/exchange/client-developer/exchange-web-services/how-to-authenticate-an-ews-application-by-using-oauth](https://docs.microsoft.com/en-us/exchange/client-developer/exchange-web-services/how-to-authenticate-an-ews-application-by-using-oauth)
- Exchange New-ApplicationAccessPolicy:  
[https://docs.microsoft.com/en-us/powershell/module/exchange/new-applicationaccesspolicy?view=exchange-ps](https://docs.microsoft.com/en-us/powershell/module/exchange/new-applicationaccesspolicy?view=exchange-ps)

## Skill-Matrix Zugriffe und Berechtigungen

Siehe README.md

### Zusammenfassung: Benoetigte Graph API Scopes fuer App Registration


| Scope                              | Benoetigende Skills                    | Zweck                                                |
| ---------------------------------- | -------------------------------------- | ---------------------------------------------------- |
| `Mail.Read`                        | mail-search, mail-agent                | Outlook-Mails durchsuchen und lesen                  |
| `Calendars.Read`                   | mail-search, mail-agent                | Kalender-Events durchsuchen                          |
| `Files.Read.All`                   | file-search, file-reader, mail-agent   | SharePoint/OneDrive-Dateien lesen                    |
| `Sites.Read.All`                   | file-search, file-reader               | SharePoint-Sites und -Listen lesen                   |
| `Chat.ReadWrite`                   | teams-chat                             | Teams-1:1-Chat senden und lesen                      |
| `User.Read`                        | teams-chat                             | Eigenes Profil und Kontakte aufloesen                |
| `Mail.Send`                        | outlook *(bei Graph-Migration)*        | Mails programmatisch senden                          |
| `Mail.ReadWrite`                   | outlook *(bei Graph-Migration)*        | Mail-Entwuerfe erstellen und verwalten               |
| `Calendars.ReadWrite`              | outlook-termin *(bei Graph-Migration)* | Termine/Meetings erstellen, aktualisieren, absagen   |
| `Chat.Read`                        | copilot-chat *(bei API-Migration)*     | Teams-Chat-Inhalte fuer Copilot-Grounding            |
| `ChannelMessage.Read.All`          | copilot-chat *(bei API-Migration)*     | Teams-Kanal-Nachrichten fuer Copilot-Grounding       |
| `People.Read.All`                  | copilot-chat *(bei API-Migration)*     | Erweiterte Personensuche fuer Copilot                |
| `OnlineMeetingTranscript.Read.All` | copilot-chat *(bei API-Migration)*     | Meeting-Transkripte fuer Copilot-Grounding           |
| `ExternalItem.Read.All`            | copilot-chat *(bei API-Migration)*     | Graph Connectors / externe Datenquellen fuer Copilot |


**5 von 35 Skills** benoetigen heute eine Microsoft App Registration (Graph API). Die restlichen 30 arbeiten rein lokal, ueber Browser-SSO, BPLUS-Kerberos oder Confluence/Jira-PAT.

**Hinweis COM → Graph Migration:** `skill-outlook` (Mail-Versand) und `skill-outlook-termin` (Termin-Versand) laufen aktuell ueber das lokale Outlook COM-Objekt und brauchen keine App Registration. Bei einer spaeteren Migration auf die Graph API kaemen 3 weitere Scopes hinzu: `Mail.Send`, `Mail.ReadWrite`, `Calendars.ReadWrite`.

**Hinweis Copilot Chat → API Migration:** `skill-m365-copilot-chat` laeuft aktuell ueber Playwright DOM-Interaktion (Browser-SSO). Fuer eine API-basierte Nutzung ueber `POST /beta/copilot/conversations` (Graph Beta) werden **7 zusaetzliche Scopes mit Admin-Consent** benoetigt — siehe Tabelle oben. Stand Maerz 2026: Die API ist Beta, der Endpoint existiert und liefert 403 ohne die nötigen Scopes. Diese Scopes sind NICHT im Standard-NAA-Token (M365ChatClient AppID c0ab8ce9) enthalten und erfordern eine **eigene App Registration mit Admin-Consent**. Details: [Analyse-m365-copilot-api-research.md](Analyse-m365-copilot-api-research.md) und [Analyse-m365-copilot-chat-skill.md](Analyse-m365-copilot-chat-skill.md).

## Beantragungskonzept: Was genau beantragt werden muss

### Empfehlung: 2 App Registrations (gestuft)

Aufgrund der unterschiedlichen Reifegrade und Scope-Anforderungen wird eine **gestufte Beantragung** empfohlen:


| #     | App Registration                   | Zeitpunkt              | Begruendung                                                                                                                                                           |
| ----- | ---------------------------------- | ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **1** | **BordnetzGPT — Core**             | Sofort beantragen      | Deckt die 5 heute aktiven Graph-Skills ab. Scopes sind stabil und produktionsreif.                                                                                    |
| **2** | **BordnetzGPT — Copilot Chat API** | Spaeter / wenn Beta→GA | 7 zusaetzliche Scopes fuer `POST /beta/copilot/conversations`. API ist Beta, Scopes sind sehr breit. Separater Antrag vermeidet Security-Diskussionen am Core-Antrag. |


---

### App Registration 1: BordnetzGPT — Core

#### Business Case und Effizienzprogramm

BordnetzGPT ist der KI-Agent fuer die Bordnetz-Entwicklungsumgebung VOBES. Die App Registration wird benoetigt, um BordnetzGPT sukzessive vom reinen Wissensassistenten zum persoenlichen VOBES-KI-Agenten auszubauen. Kernmotivation:

- **Systemschaltplan-Tracking:** Das Einholen von Systemschaltplaninformationen bei den jeweiligen Fachverantwortlichen ist ein aufwaendiges, manuelles Tracking-Geschaeft (Mails senden, Rueckmeldungen verfolgen, Termine koordinieren, Dokumente aus SharePoint zusammenfuehren). BordnetzGPT automatisiert diesen Workflow durch direkten Zugriff auf Mail, Kalender, Teams-Chat und SharePoint-Dateien.
- **Effizienzgewinn:** Statt manueller Mail-Recherche, SharePoint-Suche und Termin-Koordination uebernimmt der Agent kontextbezogen die Informationsbeschaffung und -aufbereitung — nachweisbar messbarer Zeitgewinn pro Tracking-Zyklus.
- **Skalierung:** Der Ansatz ist uebertragbar auf weitere Bordnetz-Tracking-Prozesse (Budget-Tracking, Beauftragungen, Pruefbuero-Koordination).

#### Formularfelder (gemaess Antragsformular)


| Feld                        | Wert                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Name der Applikation**    | `BordnetzGPT`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| **Verantwortlicher**        | *(E-Mail des internen MA — kein Externer)*                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| **Stellvertreter**          | *(E-Mail Stellvertreter, Semikolon-getrennt)*                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| **Kurzbeschreibung**        | BordnetzGPT — KI-Agent fuer die Bordnetz-Entwicklung (VOBES 2025). Wird sukzessive zum persoenlichen KI-Assistenten fuer Bordnetzentwickler ausgebaut. Automatisiert das aufwaendige Tracking-Geschaeft fuer Systemschaltplaninformationen (Einholen bei Fachverantwortlichen per Mail/Chat, Dokumente aus SharePoint zusammenfuehren, Termine koordinieren). Liest und sendet Mails (nach expliziter Bestätigung), Kalender-Events, SharePoint-Dateien und Teams-Chats ausschliesslich im Kontext des angemeldeten Benutzers (Delegated Permissions). Teil des Effizienzprogramms der Bordnetz-Entwicklung. |
| **ICTO / LeanIX**           | *(LeanIX-ID von BordnetzGPT eintragen — pruefen ob bereits vorhanden)*                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| **Zielgruppe**              | Einzelner authentifizierter Benutzer (Delegated Permissions) — Bordnetz-Ingenieure und Koordinatoren                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| **Supportstruktur**         | *(SC3-Gruppe / Knowledge Record angeben)*                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| **IT Sicherheitsbewertung** | *(ITSB-Nummer falls vorhanden)*                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| **Betriebsrat**             | *(Nachweis ueber BR-Vorlage — relevant wegen Mail-/Chat-Zugriff)*                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| **Applikations Typ**        | App Registration                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |


#### Auth-Flow und Technische Konfiguration


| Parameter               | Wert                                                        | Begruendung                                                                                                                      |
| ----------------------- | ----------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| **Berechtigungstyp**    | **Delegated Permissions**                                   | Agent arbeitet immer im Kontext des angemeldeten Benutzers. Kein Daemon/Service.                                                 |
| **Auth Flow**           | Authorization Code Flow mit PKCE                            | VW Conditional Access blockiert Device Code Flow (Error 53003). PKCE ist der empfohlene Flow fuer Public Clients / Desktop-Apps. |
| **Redirect URI**        | `http://localhost:{port}`                                   | Lokaler Callback fuer den Desktop-Agenten. Exakter Port bei Konfiguration festlegen.                                             |
| **Client Type**         | Public Client (kein Secret noetig bei PKCE)                 | Desktop-App, kein Server-Szenario. Alternativ: Confidential Client mit Zertifikat falls spaeter Service-Betrieb.                 |
| **Zertifikat / Secret** | Nur bei Confidential Client noetig — sonst PKCE ohne Secret | Empfehlung: mit Zertifikat statt Secret falls Client Credential Flow spaeter benoetigt wird.                                     |


#### Benoetigte Delegated Permissions (Graph API)


| Scope                     | Skills                               | Zweck                                              | Sensitivity                           |
| ------------------------- | ------------------------------------ | -------------------------------------------------- | ------------------------------------- |
| `**Mail.Read**`           | mail-search, mail-agent              | Outlook-Mails des Users durchsuchen und lesen      | Mittel — liest nur eigenes Postfach   |
| `**Mail.Send**`           | outlook *(Graph-Migration)*          | Mails programmatisch senden im Namen des Users     | Hoch — Sendeberechtigung, BR-relevant |
| `**Mail.ReadWrite**`      | outlook *(Graph-Migration)*          | Mail-Entwuerfe erstellen und verwalten             | Mittel                                |
| `**Calendars.Read**`      | mail-search, mail-agent              | Kalender-Events des Users durchsuchen              | Niedrig                               |
| `**Calendars.ReadWrite**` | outlook-termin *(Graph-Migration)*   | Termine/Meetings erstellen, aktualisieren, absagen | Mittel — schreibt Kalender            |
| `**Files.Read.All**`      | file-search, file-reader, mail-agent | SharePoint/OneDrive-Dateien lesen                  | Mittel — tenant-weiter Lesezugriff    |
| `**Sites.Read.All**`      | file-search, file-reader             | SharePoint-Sites und -Listen lesen                 | Mittel — tenant-weiter Lesezugriff    |
| `**Chat.ReadWrite**`      | teams-chat                           | Teams-1:1-Chats senden und lesen                   | Hoch — liest/schreibt Chat-Inhalte    |
| `**User.Read**`           | teams-chat                           | Eigenes Profil und Kontakte aufloesen              | Niedrig                               |
| `**People.Read**`         | personensuche *(optional)*           | Personenvorschlaege / Kontakte                     | Niedrig                               |


**Hinweis `Files.Read.All` vs `Sites.Selected`:** Die SharePoint-Governance-Seite empfiehlt `Sites.Selected` als Least-Privilege-Ansatz. Fuer diesen Agenten wird allerdings tenant-weiter Lesezugriff benoetigt (der User sucht Dateien in beliebigen Sites, auf die er selbst Zugriff hat). Da Delegated Permissions verwendet werden, greift ohnehin die Berechtigung des angemeldeten Users als Obergrenze — `Files.Read.All` delegiert ist daher sicher, weil der User nur sieht, worauf er selbst Zugriff hat.

**Hinweis `Mail.Send` und `Chat.ReadWrite`:** Diese Scopes sind besonders sensitiv (Betriebsrat, Datenschutz). Im Antrag begruenden mit: Agent sendet nur auf explizite Useranweisung, nie automatisch. Alle Drafts werden vor Versand angezeigt.

#### Abgrenzung: Was NICHT beantragt werden muss


| Zugriff                                           | Grund                                |
| ------------------------------------------------- | ------------------------------------ |
| BPLUS REST API                                    | Kerberos-Auth, kein Entra ID         |
| Confluence / Jira                                 | PAT-basiert, eigene Infrastruktur    |
| GroupFind API                                     | Keycloak-Auth via Browser-SSO        |
| SharePoint REST (skill-sharepoint)                | Browser-SSO via Playwright           |
| iProject (TE Regelwerk)                           | Browser-SSO via Playwright           |
| Outlook COM (skill-outlook, skill-outlook-termin) | Lokale COM-Schnittstelle, kein Graph |
| ChatGPT Research                                  | Browser-SSO, kein VW-Tenant          |
| local_rag, Excel, File-Converter, Hibernate       | Rein lokal                           |


---

### App Registration 2: BordnetzGPT — Copilot Chat API (spaeter)

**Status:** Beta API (`POST /beta/copilot/conversations`). Erst beantragen wenn API GA wird oder konkreter Bedarf besteht.

#### Zusaetzliche Delegated Permissions (ueber Core hinaus)


| Scope                                  | Zweck                                          | Status                                 |
| -------------------------------------- | ---------------------------------------------- | -------------------------------------- |
| `**Chat.Read**`                        | Teams-Chat-Inhalte fuer Copilot-Grounding      | Upgrade von `Chat.ReadBasic`           |
| `**ChannelMessage.Read.All**`          | Teams-Kanal-Nachrichten fuer Copilot-Grounding | Hoch — tenant-weiter Kanal-Lesezugriff |
| `**People.Read.All**`                  | Erweiterte Personensuche (.All statt .Read)    | Upgrade von `People.Read`              |
| `**OnlineMeetingTranscript.Read.All**` | Meeting-Transkripte fuer Copilot               | Hoch — liest Transkripte               |
| `**ExternalItem.Read.All**`            | Graph Connectors / externe Quellen             | Hoch — Zugriff auf externe Daten       |
| `**Sites.Read.All**`                   | Bereits in Core enthalten                      | Duplikat — kein Zusatzaufwand          |
| `**Mail.Read**`                        | Bereits in Core enthalten                      | Duplikat — kein Zusatzaufwand          |


**Achtung:** Die API verlangt Admin-Consent fuer diese Scopes. Das erhoehte Scope-Profil (`ChannelMessage.Read.All`, `OnlineMeetingTranscript.Read.All`, `ExternalItem.Read.All`) wird wahrscheinlich eine vertieftere Security-Bewertung erfordern.

---

### Voraussetzungen vor Antragstellung (Checkliste)


| #   | Voraussetzung                                                     | Status | Quelle                 |
| --- | ----------------------------------------------------------------- | ------ | ---------------------- |
| 1   | LeanIX/ICTO-Eintrag existiert                                     | ☐      | Prozessseite, Formular |
| 2   | Schnittstellenbeschreibung erstellt                               | ☐      | Prozessseite           |
| 3   | IT-Sicherheitsbewertung (markenspezifisch)                        | ☐      | Prozessseite           |
| 4   | Datenschutzbewertung vorhanden                                    | ☐      | Prozessseite           |
| 5   | Betriebsratsvorlage (wg. Mail/Chat-Zugriff)                       | ☐      | Formular, Prozessseite |
| 6   | Verantwortlicher + Stellvertreter benannt (intern, kein Externer) | ☐      | Formular               |
| 7   | Supportstruktur / SC3-Gruppe definiert                            | ☐      | Formular               |
| 8   | Admin-User fuer DEV-Tenant beantragt (WBT-Schulung absolviert)    | ☐      | Admin-User-Seite       |
| 9   | Test-User fuer DEV-Tenant beantragt                               | ☐      | Test-User-Seite        |
| 10  | Betriebs- und Berechtigungskonzept dokumentiert                   | ☐      | Prozessseite           |


### Ablauf nach Antragstellung

```
1. Antrag ueber SharePoint-Formular einreichen
   → Automatisch Service Change in Azure DevOps
   
2. GTA legt App Registration im DEV-Tenant an
   
3. Projekt konfiguriert im DEV:
   - Redirect URI (http://localhost:{port})
   - API Permissions (Delegated, s.o.)
   - Optional: Zertifikat hinterlegen
   
4. Admin-Consent im DEV durch GTA/Admin

5. E2E-Tests mit Test-User:
   - Mail lesen/senden
   - Kalender lesen/schreiben
   - SharePoint-Dateien suchen/lesen
   - Teams-Chat senden/lesen
   - Nachweis dokumentieren
   
6. Freigaben einholen:
   - IT-Security-Freigabe
   - Datenschutz-Freigabe
   - LeanIX-Hinterlegung pruefen
   
7. GTA ueberfuehrt 1:1 nach PROD
   
8. Lifecycle: Jaehrlicher Review (sonst Deaktivierung)
```

### Offene Entscheidungen


| #   | Entscheidung                                              | Optionen                                                                                           | Empfehlung                                                                            |
| --- | --------------------------------------------------------- | -------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| 1   | Public Client (PKCE) vs. Confidential Client (Zertifikat) | PKCE: kein Secret noetig, einfacher. Zertifikat: sicherer, ermoeglicht spaeter Client Credentials. | **PKCE fuer Start**, Zertifikat spaeter wenn Service-Betrieb geplant.                 |
| 2   | Alle Scopes sofort oder stufenweise?                      | Sofort: ein Antrag, einfacher. Stufenweise: zuerst read-only, spaeter send.                        | **Alle Core-Scopes sofort** — vermeidet Mehrfach-Antraege und SC3-Aenderungsrequests. |
| 3   | `Sites.Read.All` vs. `Sites.Selected`                     | `.Read.All`: tenant-weit, flexibler. `.Selected`: Least-Privilege, site-spezifisch.                | `**.Read.All` (Delegated)** — effektiver Zugriff begrenzt durch User-Berechtigungen.  |
| 4   | Copilot Chat API jetzt oder spaeter?                      | Jetzt: alle Scopes in einem Antrag. Spaeter: trennt Risiko.                                        | **Spaeter** — Beta-API, sehr breite Scopes, eigene Security-Bewertung noetig.         |
| 5   | Funktionspostfach oder persoenliches Postfach?            | Funktionspostfach: Application Permissions + Access Policy. Persoenlich: Delegated.                | **Persoenlich (Delegated)** — Agent arbeitet immer als der angemeldete User.          |


## Projektnaechste sinnvolle Schritte

1. Interne Zielarchitektur fuer dieses Repo verbindlich festlegen (Mail, Teams, ggf. weitere APIs) und Berechtigungen minimieren.
2. Antragsentwurf vorbereiten inklusive LeanIX/ICTO, Security, Datenschutz und Betriebskonzept.
3. Technisches Dev-Testpaket definieren (Testuser, Proxy, Zertifikat/Secret, Testfaelle) und vor Prod-Uebernahme nachweisfaehig dokumentieren.