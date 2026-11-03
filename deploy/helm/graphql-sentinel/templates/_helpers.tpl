{{- define "sentinel.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "sentinel.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name (include "sentinel.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "sentinel.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
app.kubernetes.io/name: {{ include "sentinel.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "sentinel.selector" -}}
app.kubernetes.io/name: {{ include "sentinel.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "sentinel.image" -}}
{{- $repo := .Values.image.repository -}}
{{- if eq .Values.mode "extproc" -}}{{- $repo = .Values.image.extprocRepository -}}{{- end -}}
{{- printf "%s:%s" $repo (default .Chart.AppVersion .Values.image.tag) -}}
{{- end -}}

{{- define "sentinel.tokenSecret" -}}
{{- if .Values.auth.existingSecret -}}{{ .Values.auth.existingSecret }}{{- else -}}{{ include "sentinel.fullname" . }}-auth{{- end -}}
{{- end -}}

{{- define "sentinel.upstreamUrl" -}}
{{- if eq .Values.mode "sidecar" -}}
{{- printf "http://127.0.0.1:%v%s" .Values.sidecar.appPort .Values.sidecar.appPath -}}
{{- else -}}
{{- required "upstream.url is required in gateway mode" .Values.upstream.url -}}
{{- end -}}
{{- end -}}

{{- define "sentinel.hasSchema" -}}
{{- if or .Values.schema.sdl .Values.schema.existingConfigMap -}}true{{- end -}}
{{- end -}}

{{/* Environment shared by every Sentinel container. */}}
{{- define "sentinel.env" -}}
- name: SENTINEL_ENFORCEMENT
  value: {{ .Values.sentinel.enforcement | quote }}
- name: SENTINEL_INTROSPECTION
  value: {{ .Values.sentinel.introspection | quote }}
- name: SENTINEL_TRUST_PROXY_HEADERS
  value: {{ .Values.sentinel.trustProxyHeaders | quote }}
- name: SENTINEL_GATEWAY__BATCHING
  value: {{ .Values.sentinel.batching | quote }}
- name: SENTINEL_GATEWAY__MASK_FIELD_SUGGESTIONS
  value: {{ .Values.sentinel.maskFieldSuggestions | quote }}
- name: SENTINEL_TELEMETRY__DECISION_LOG
  value: {{ .Values.telemetry.decisionLog | quote }}
{{- if .Values.telemetry.otlpEndpoint }}
- name: SENTINEL_TELEMETRY__ENABLED
  value: "true"
- name: SENTINEL_OTLP_ENDPOINT
  value: {{ .Values.telemetry.otlpEndpoint | quote }}
{{- end }}
{{- if include "sentinel.hasSchema" . }}
- name: SENTINEL_SCHEMA_PATH
  value: /config/schema/schema.graphql
- name: SENTINEL_GRAPHQL_SCHEMA__DEFAULT_LIST_SIZE
  value: {{ .Values.schema.defaultListSize | quote }}
{{- end }}
{{- if ne .Values.persistedQueries.mode "off" }}
- name: SENTINEL_PERSISTED_MODE
  value: {{ .Values.persistedQueries.mode | quote }}
- name: SENTINEL_PERSISTED_MANIFEST
  value: /config/persisted/manifest.json
{{- end }}
{{- range $k, $v := .Values.sentinel.limits }}
- name: SENTINEL_LIMITS__{{ $k | upper }}
  value: {{ $v | quote }}
{{- end }}
{{- range $k, $v := .Values.sentinel.throttle }}
- name: SENTINEL_THROTTLE__{{ $k | upper }}
  value: {{ $v | quote }}
{{- end }}
{{- with .Values.sentinel.extraEnv }}
{{ toYaml . }}
{{- end }}
{{- end -}}

{{- define "sentinel.volumes" -}}
- name: tmp
  emptyDir: {}
- name: data
{{- if .Values.persistence.enabled }}
  persistentVolumeClaim:
    claimName: {{ include "sentinel.fullname" . }}
{{- else }}
  emptyDir: {}
{{- end }}
{{- if include "sentinel.hasSchema" . }}
- name: schema
  configMap:
    name: {{ default (printf "%s-schema" (include "sentinel.fullname" .)) .Values.schema.existingConfigMap }}
{{- end }}
{{- if ne .Values.persistedQueries.mode "off" }}
- name: persisted
  configMap:
    name: {{ default (printf "%s-persisted" (include "sentinel.fullname" .)) .Values.persistedQueries.existingConfigMap }}
{{- end }}
{{- end -}}

{{- define "sentinel.mounts" -}}
- name: tmp
  mountPath: /tmp
- name: data
  mountPath: /data
{{- if include "sentinel.hasSchema" . }}
- name: schema
  mountPath: /config/schema
  readOnly: true
{{- end }}
{{- if ne .Values.persistedQueries.mode "off" }}
- name: persisted
  mountPath: /config/persisted
  readOnly: true
{{- end }}
{{- end -}}

{{- define "sentinel.securityContext" -}}
allowPrivilegeEscalation: false
readOnlyRootFilesystem: true
runAsNonRoot: true
runAsUser: 10001
capabilities:
  drop: [ALL]
seccompProfile:
  type: RuntimeDefault
{{- end -}}
