# Instalador RISKO Mac

Distribucion independiente de Portal RISKO para equipos Apple Silicon ARM64.
No reemplaza ni modifica el launcher, el instalador, los releases o el
manifiesto de Windows.

## Artefactos Mac

El proceso genera y publica unicamente estos elementos:

```text
Sistema Portal/
├── portal-macos.json
├── Instalador/
│   └── Instalador RISKO Mac.pkg
└── Versiones Mac/
    └── 2.1.9/
        └── Portal-RISKO-macOS-arm64.zip
```

`portal.json`, `Instalar Portal RISKO.exe` y `Versiones/` siguen siendo
exclusivos del flujo Windows.

## Construccion en el primer Mac ARM64

Apple exige que los bundles e instaladores macOS se construyan en macOS. En el
Mac de oficina, abra primero la carpeta compartida y ejecute en Terminal:

```bash
cd "/Volumes/Gerencia_Riesgo_De_Tesoreria/3 Jefatura de Riesgo de Mercado/Proyecto Risko/portal/macos"
chmod +x construir_instalador_risko_mac.sh "Construir Instalador RISKO Mac.command"
./construir_instalador_risko_mac.sh \
  --publish-root "/Volumes/Gerencia_Riesgo_De_Tesoreria/Portal Riesgos de Mercado"
```

Si se requiere trasladar los fuentes fuera del proyecto compartido, use
`paquete-construccion/Preparar Instalador RISKO Mac ARM64.zip`, descomprímalo en
el Mac y ejecute el mismo comando dentro de su carpeta `portal/macos`.

También se puede abrir `Construir Instalador RISKO Mac.command`; si encuentra
la unidad en una de las rutas estándar, construye y publica automáticamente.
Para crear los archivos localmente sin publicarlos, ejecute el `.sh` sin
`--publish-root`. La salida queda en:

```text
portal/macos/dist-macos/Instalador RISKO Mac.pkg
```

Requisitos del equipo constructor:

- Apple Silicon ARM64;
- Python 3.11 o posterior con tkinter;
- acceso de lectura al proyecto y de escritura a producción si se publica;
- acceso a internet o a un repositorio interno de paquetes Python durante la
  primera construcción.

## Firma y notarización

Para la entrega general, configure las identidades corporativas antes de
construir:

```bash
export RISKO_APPLE_APPLICATION_IDENTITY="Developer ID Application: ..."
export RISKO_APPLE_INSTALLER_IDENTITY="Developer ID Installer: ..."
export RISKO_APPLE_NOTARY_PROFILE="risko-notary"
```

El perfil se crea una sola vez con `xcrun notarytool store-credentials`. Si no
se suministran estas variables, se genera un `.pkg` piloto sin notarizar; su
instalación debe ser autorizada por TI en el Mac de prueba.

## Operación y actualización

El `.pkg` instala el launcher fijo como `/Applications/Portal RISKO.app`. Al
abrirlo:

1. busca la carpeta productiva ya montada;
2. si no está disponible, solicita a Finder montar
   `smb://ISILONSMBPROD/Gerencia_Riesgo_De_Tesoreria`;
3. consulta únicamente `Sistema Portal/portal-macos.json`;
4. copia y valida el release ARM64 bajo
   `~/Library/Application Support/PortalRisko/App`;
5. inicia la aplicación local apuntando a los dashboards compartidos.

El launcher conserva el último manifiesto y release válidos para contingencia.
Los ejecutables `.exe` de `Aplicaciones` no se muestran en Mac porque no son
compatibles con macOS.

## Validación mínima del piloto

Antes de compartir el instalador con otros usuarios, comprobar en el primer Mac:

- instalación y apertura desde `/Applications`;
- montaje SMB con VPN y autenticación corporativa;
- lectura de `Dashboards` y apertura de un tablero;
- cierre y segunda apertura usando el caché local;
- publicación de una nueva versión Mac y actualización automática;
- comportamiento sin red usando la última versión almacenada.
