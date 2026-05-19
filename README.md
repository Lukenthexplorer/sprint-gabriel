# Gabriel — Dataset para Sprint INSPER

Snapshot dos dados operacionais da Gabriel disponibilizado para a sprint de 3 semanas com o INSPER. Os 4 arquivos abaixo cobrem ocorrências analisadas pela Central de Monitoramento, Camaleões instalados, desfechos policiais e a ponte ocorrência ↔ Camaleão.

**Data do snapshot:** 18/05/2026
**Período coberto:** maio/2020 — maio/2026 (~6 anos)
**Geografia:** SP, RJ, MG

Os arquivos estão na codificação UTF-8, separador `,`, quebras de linha Unix.

---

## Arquivos

### `ocorrencias.csv` (18.895 linhas)

Ocorrências criminais e de segurança analisadas pela Central de Monitoramento Gabriel.

| Coluna | Descrição |
|---|---|
| `IDOcorrencia` | Identificador único da ocorrência |
| `NaturezaCrime` | Agrupador top-level (ex: "Roubo ou Furto"). Pode estar em branco em registros antigos. |
| `CategoriaCrime` | Categoria do crime (ex: "Furto", "Roubo", "Colisão entre Veículos") |
| `SubcategoriaCrime` | Tipo específico (ex: "Furto a Estabelecimento", "Roubo de Pertences Pessoais", "Furto de Peças de Veículo") |
| `GeneroLocal` | Tipo de local da ocorrência ("Residencial", "Comercial", "Público", "Empresarial") |
| `DataOcorrencia` | Data do evento (YYYY-MM-DD) |
| `Horario` | Horário relatado pelo solicitante (texto livre) |
| `Intervalo` | Faixa horária derivada do `Horario` (formato "HHh - HHh") |
| `Latitude`, `Longitude` | Coordenadas geográficas em graus decimais |
| `Bairro`, `Zona`, `Cidade`, `Estado` | Localização administrativa |
| `Origem` | Quem originou a solicitação (Cliente, Polícia, etc.) |
| `TipoSolicitante` | Categoria de quem pediu a análise |
| `EfetividadeAnalise` | Resultado da análise forense da Central |
| `EtapaPipeline` | Etapa atual do ticket dentro do pipeline da Central |
| `TempoParaFechamentoMs` | Tempo entre criação e fechamento do ticket, em milissegundos (nulo se ainda aberto) |

### `sensores.csv` (18.634 linhas)

Camaleões instalados com assinatura ativa. **Cada linha é uma câmera individual** — um Camaleão é composto por mais de uma câmera, então para contar Camaleões use `IDDispositivo` distinto.

| Coluna | Descrição |
|---|---|
| `IDPontoVisualizacao` | Identificador único da câmera dentro do sistema |
| `IDCamera` | Identificador único da câmera (hardware) |
| `IDDispositivo` | **Identificador da unidade Camaleão** — use para contar Camaleões |
| `IDLocal` | Identificador do local (endereço) onde o Camaleão está instalado |
| `Latitude`, `Longitude` | Coordenadas geográficas |
| `Bairro`, `Zona`, `Cidade`, `Estado` | Localização administrativa |
| `StatusConexaoCamera` | Status atual de conexão da câmera |
| `DataInicioServico` | Data em que o Camaleão começou a operar |

### `desfechos.csv` (5.407 linhas)

Desfechos policiais associados às ocorrências (prisões, recuperações, indiciamentos).

| Coluna | Descrição |
|---|---|
| `IDDesfecho` | Identificador único do desfecho |
| `IDsOcorrenciasAssociadas` | String com 1+ IDs de `IDOcorrencia` separados por vírgula |
| `DataDoDesfecho` | Data do desfecho (YYYY-MM-DD) |
| `TipoDeDesfecho` | Tipo (ex: "Indiciado", "Inocente", "Recuperado") |
| `FoiDesfechoValido` | "Sim" / "Não" |
| `FonteDoDesfecho` | Origem da informação do desfecho |
| `BaseParaDesfecho` | Base para o desfecho |
| `Bairro`, `Zona`, `Cidade`, `Estado` | Localização administrativa |
| `TextoRelatorioDesfecho` | Texto narrativo curado pelo time de marketing (quando aplicável) |
| `LegendaDoDesfecho` | Legenda curta do desfecho |
| `ResumoOcorrencia` | Resumo da ocorrência associada |
| `PodeDivulgar` | "Sim" / "Não" — indica se o desfecho pode ser divulgado publicamente |

### `ocorrencia_local.csv` (30.240 linhas)

Tabela ponte entre `ocorrencias` e `sensores`. Uma ocorrência pode estar associada a múltiplos Camaleões (via `IDLocal`), e um Camaleão pode estar associado a múltiplas ocorrências.

| Coluna | Descrição |
|---|---|
| `IDOcorrencia` | FK para `ocorrencias.IDOcorrencia` |
| `IDLocal` | FK para `sensores.IDLocal` |

---

## Notas de uso

- **Privacidade.** Estes datasets passaram por um pipeline interno que removeu PII. Nunca usem nomes próprios, endereços específicos, placas ou CPF em entregáveis. Granularidade geográfica mínima nos outputs: **bairro/zona**.
- **Snapshot diário.** Em produção, esses dados são exportados diariamente do Redshift para S3. Para a sprint, vocês recebem um snapshot pontual — não há atualização durante a sprint.
- **Linguagem em visualizações para usuário final.** Use **"ocorrências"** (não "casos" ou "situações"), **"Camaleão"** (não "câmera"), **"entorno" ou "vizinhança"** (não "raio de 500 metros").
- **Dados externos.** Quando o problema pedir, vocês mesmos coletam (SSP-SP, ISP-RJ, SES-MG, portais de notícia, IBGE). Esses não estão nesse pacote.

## Contato

Felipe Araujo — felipe@gabriel.com.br
