import { Injectable, signal } from '@angular/core';

export type Language = 'en' | 'pt-BR';

export interface TranslationEntry {
  en: string;
  'pt-BR': string;
}

const STORAGE_KEY = 'pudimjobs_language';

/**
 * Translation dictionary for the PudimJobs frontend.
 * Every user-facing string lives here in English (`en`) and Brazilian
 * Portuguese (`pt-BR`). Keys are dot-namespaced by feature/domain.
 */
export const DICTIONARY: Record<string, TranslationEntry> = {
  // ---- App shell -----------------------------------------------------------
  'app.skipToContent': { en: 'Skip to content', 'pt-BR': 'Pular para o conteúdo' },
  'app.title': { en: 'PudimJobs — Job Application Tracker', 'pt-BR': 'PudimJobs — Rastreador de Candidaturas' },
  'app.description': {
    en: 'Scrape job listings, tailor your CV, and track applications from saved to offer.',
    'pt-BR': 'Colete listagens de vagas, personalize seu CV e acompanhe candidaturas de salva até a oferta.',
  },

  // ---- Common --------------------------------------------------------------
  'common.cancel': { en: 'Cancel', 'pt-BR': 'Cancelar' },
  'common.save': { en: 'Save', 'pt-BR': 'Salvar' },
  'common.delete': { en: 'Delete', 'pt-BR': 'Excluir' },
  'common.edit': { en: 'Edit', 'pt-BR': 'Editar' },
  'common.close': { en: 'Close', 'pt-BR': 'Fechar' },
  'common.remove': { en: 'Remove', 'pt-BR': 'Remover' },
  'common.name': { en: 'Name', 'pt-BR': 'Nome' },
  'common.type': { en: 'Type', 'pt-BR': 'Tipo' },
  'common.company': { en: 'Company', 'pt-BR': 'Empresa' },
  'common.title': { en: 'Title', 'pt-BR': 'Título' },
  'common.url': { en: 'URL', 'pt-BR': 'URL' },
  'common.tags': { en: 'Tags', 'pt-BR': 'Tags' },
  'common.description': { en: 'Description', 'pt-BR': 'Descrição' },
  'common.skills': { en: 'Skills:', 'pt-BR': 'Habilidades:' },
  'common.experience': { en: 'Experience:', 'pt-BR': 'Experiência:' },
  'common.education': { en: 'Education:', 'pt-BR': 'Formação:' },
  'common.years': { en: 'years', 'pt-BR': 'anos' },
  'common.previous': { en: 'Previous', 'pt-BR': 'Anterior' },
  'common.next': { en: 'Next', 'pt-BR': 'Próximo' },
  'common.auth': { en: 'Auth', 'pt-BR': 'Autenticação' },
  'common.apiKey': { en: 'API key', 'pt-BR': 'chave de API' },
  'common.actions': { en: 'Actions', 'pt-BR': 'Ações' },
  'common.jobs': { en: 'Jobs', 'pt-BR': 'Vagas' },
  'common.sources': { en: 'Sources', 'pt-BR': 'Fontes' },
  'common.health': { en: 'Health', 'pt-BR': 'Saúde' },
  'common.status': { en: 'Status', 'pt-BR': 'Status' },
  'common.active': { en: 'Active', 'pt-BR': 'Ativa' },
  'common.paused': { en: 'Paused', 'pt-BR': 'Pausada' },
  'common.yes': { en: 'Yes', 'pt-BR': 'Sim' },

  // ---- Layout / sidebar ----------------------------------------------------
  'layout.nav.jobs': { en: 'Jobs', 'pt-BR': 'Vagas' },
  'layout.nav.sources': { en: 'Sources', 'pt-BR': 'Fontes' },
  'layout.nav.masterCv': { en: 'Master CV', 'pt-BR': 'CV principal' },
  'layout.nav.applications': { en: 'Applications', 'pt-BR': 'Candidaturas' },
  'layout.nav.alerts': { en: 'Alerts', 'pt-BR': 'Alertas' },
  'layout.nav.notifications': { en: 'Notifications', 'pt-BR': 'Notificações' },
  'layout.nav.admin': { en: 'Admin', 'pt-BR': 'Admin' },
  'layout.aria.closeNav': { en: 'Close navigation menu', 'pt-BR': 'Fechar menu de navegação' },
  'layout.aria.mainNav': { en: 'Main navigation', 'pt-BR': 'Navegação principal' },
  'layout.aria.openNav': { en: 'Open navigation menu', 'pt-BR': 'Abrir menu de navegação' },
  'layout.aria.switchToPortuguese': { en: 'Switch language to Portuguese', 'pt-BR': 'Mudar o idioma para português' },
  'layout.aria.switchToEnglish': { en: 'Switch language to English', 'pt-BR': 'Mudar o idioma para inglês' },
  'layout.apiOnline': { en: 'API online', 'pt-BR': 'API online' },
  'layout.apiUnreachable': { en: 'API unreachable', 'pt-BR': 'API indisponível' },
  'layout.switchToLight': { en: 'Switch to light mode', 'pt-BR': 'Mudar para o modo claro' },
  'layout.switchToDark': { en: 'Switch to dark mode', 'pt-BR': 'Mudar para o modo escuro' },
  'layout.lightMode': { en: 'Light mode', 'pt-BR': 'Modo claro' },
  'layout.darkMode': { en: 'Dark mode', 'pt-BR': 'Modo escuro' },
  'layout.signOut': { en: 'Sign out', 'pt-BR': 'Sair' },

  // ---- Login ---------------------------------------------------------------
  'login.tagline': { en: 'Job Application Tracker', 'pt-BR': 'Rastreador de Candidaturas de Emprego' },
  'login.email': { en: 'Email', 'pt-BR': 'E-mail' },
  'login.emailRequired': { en: 'Email is required.', 'pt-BR': 'O e-mail é obrigatório.' },
  'login.emailInvalid': { en: 'Enter a valid email address.', 'pt-BR': 'Digite um endereço de e-mail válido.' },
  'login.password': { en: 'Password', 'pt-BR': 'Senha' },
  'login.hidePassword': { en: 'Hide password', 'pt-BR': 'Ocultar senha' },
  'login.showPassword': { en: 'Show password', 'pt-BR': 'Mostrar senha' },
  'login.passwordRequired': { en: 'Password is required.', 'pt-BR': 'A senha é obrigatória.' },
  'login.passwordMinLength': { en: 'Password must be at least 6 characters.', 'pt-BR': 'A senha deve ter pelo menos 6 caracteres.' },
  'login.signingIn': { en: 'Signing in…', 'pt-BR': 'Entrando…' },
  'login.signIn': { en: 'Sign in', 'pt-BR': 'Entrar' },
  'login.invalidCredentials': { en: 'Invalid email or password', 'pt-BR': 'E-mail ou senha inválidos' },

  // ---- Jobs ----------------------------------------------------------------
  'jobs.title': { en: 'Jobs', 'pt-BR': 'Vagas' },
  'jobs.addJob': { en: 'Add job', 'pt-BR': 'Adicionar vaga' },
  'jobs.searchKeywordsPlaceholder': { en: 'Keywords (title, company, description)', 'pt-BR': 'Palavras-chave (título, empresa, descrição)' },
  'jobs.aria.searchKeywords': { en: 'Search keywords', 'pt-BR': 'Buscar palavras-chave' },
  'jobs.aria.filterCompany': { en: 'Filter by company', 'pt-BR': 'Filtrar por empresa' },
  'jobs.aria.filterTags': { en: 'Filter by tags', 'pt-BR': 'Filtrar por tags' },
  'jobs.aria.afterDate': { en: 'Posted after date', 'pt-BR': 'Publicada após' },
  'jobs.aria.beforeDate': { en: 'Posted before date', 'pt-BR': 'Publicada antes de' },
  'jobs.tagsPlaceholder': { en: 'Tags (comma separated)', 'pt-BR': 'Tags (separadas por vírgula)' },
  'jobs.searching': { en: 'Searching…', 'pt-BR': 'Buscando…' },
  'jobs.search': { en: 'Search', 'pt-BR': 'Buscar' },
  'jobs.addJobManually': { en: 'Add job manually', 'pt-BR': 'Adicionar vaga manualmente' },
  'jobs.titlePlaceholder': { en: 'Senior Python Engineer', 'pt-BR': 'Engenheiro(a) Python Sênior' },
  'jobs.postedDate': { en: 'Posted date', 'pt-BR': 'Data de publicação' },
  'jobs.descriptionPlaceholder': { en: 'Full job description…', 'pt-BR': 'Descrição completa da vaga…' },
  'jobs.noJobsFound': { en: 'No jobs found', 'pt-BR': 'Nenhuma vaga encontrada' },
  'jobs.noJobsHint': { en: 'Try adjusting your search filters, or add a job manually to get started.', 'pt-BR': 'Tente ajustar os filtros de busca ou adicione uma vaga manualmente para começar.' },
  'jobs.addFirstJob': { en: 'Add your first job', 'pt-BR': 'Adicione sua primeira vaga' },
  'jobs.postedPrefix': { en: 'Posted', 'pt-BR': 'Publicada em' },
  'jobs.pagination': { en: 'Jobs pagination', 'pt-BR': 'Paginação de vagas' },
  'jobs.zeroResults': { en: '0 results', 'pt-BR': '0 resultados' },
  'jobs.rangeLabel': { en: '{start}–{end} of {total}', 'pt-BR': '{start}–{end} de {total}' },
  'jobs.jobAdded': { en: 'Job added successfully.', 'pt-BR': 'Vaga adicionada com sucesso.' },
  'jobs.hideApplied': { en: 'Hide applied jobs', 'pt-BR': 'Ocultar vagas já candidatadas' },
  'jobs.showHidden': { en: 'Show hidden jobs', 'pt-BR': 'Mostrar vagas ocultas' },
  'jobs.hiddenBadge': { en: 'Hidden', 'pt-BR': 'Oculta' },
  'jobs.hide': { en: 'Hide', 'pt-BR': 'Ocultar' },
  'jobs.unhide': { en: 'Show job', 'pt-BR': 'Mostrar vaga' },
  'jobs.jobHidden': { en: 'Job hidden.', 'pt-BR': 'Vaga ocultada.' },
  'jobs.jobUnhidden': { en: 'Job is visible again.', 'pt-BR': 'Vaga visível novamente.' },

  // ---- Application pipeline statuses ---------------------------------------
  'pipeline.saved': { en: 'Saved', 'pt-BR': 'Salva' },
  'pipeline.applied': { en: 'Applied', 'pt-BR': 'Candidatada' },
  'pipeline.interview': { en: 'Interview', 'pt-BR': 'Entrevista' },
  'pipeline.offer': { en: 'Offer', 'pt-BR': 'Oferta' },
  'pipeline.rejected': { en: 'Rejected', 'pt-BR': 'Rejeitada' },
  'pipeline.inPipeline': { en: 'In pipeline', 'pt-BR': 'No pipeline' },

  // ---- Job detail ----------------------------------------------------------
  'jobDetail.backToJobs': { en: 'Back to jobs', 'pt-BR': 'Voltar para as vagas' },
  'jobDetail.parsingQueued': { en: 'Parsing job description… refresh to see results.', 'pt-BR': 'Analisando a descrição da vaga… atualize para ver os resultados.' },
  'jobDetail.parsingQueuedToast': { en: 'Job parsing has been queued.', 'pt-BR': 'A análise da vaga foi enfileirada.' },
  'jobDetail.addedToPipeline': { en: 'Added to your application pipeline.', 'pt-BR': 'Adicionada ao seu pipeline de candidaturas.' },
  'jobDetail.couldNotAdd': { en: 'Could not add the application.', 'pt-BR': 'Não foi possível adicionar a candidatura.' },
  'jobDetail.tailoringStarted': { en: 'Tailoring started. Download the result from the CV page.', 'pt-BR': 'Personalização iniciada. Baixe o resultado na página do CV.' },
  'jobDetail.tailoringStartedToast': { en: 'Tailoring started — see the CV page for your PDF.', 'pt-BR': 'Personalização iniciada — veja a página do CV para o seu PDF.' },
  'jobDetail.failedTailoring': { en: 'Failed to start tailoring (is there a master CV yet?).', 'pt-BR': 'Falha ao iniciar a personalização (já existe um CV principal?).' },
  'jobDetail.failedTailoringToast': { en: 'Failed to start tailoring — is there a master CV yet?', 'pt-BR': 'Falha ao iniciar a personalização — já existe um CV principal?' },
  'jobDetail.viewOriginal': { en: 'View original posting', 'pt-BR': 'Ver publicação original' },
  'jobDetail.adding': { en: 'Adding…', 'pt-BR': 'Adicionando…' },
  'jobDetail.addToApplications': { en: 'Add to applications', 'pt-BR': 'Adicionar às candidaturas' },
  'jobDetail.tailoring': { en: 'Tailoring…', 'pt-BR': 'Personalizando…' },
  'jobDetail.tailorCv': { en: 'Tailor CV for this job', 'pt-BR': 'Personalizar CV para esta vaga' },
  'jobDetail.parsedRequirements': { en: 'Parsed job requirements', 'pt-BR': 'Requisitos analisados da vaga' },
  'jobDetail.notParsed': { en: 'Not parsed yet.', 'pt-BR': 'Ainda não analisada.' },
  'jobDetail.parseNow': { en: 'Parse now', 'pt-BR': 'Analisar agora' },
  'jobDetail.noDescription': { en: 'No description provided.', 'pt-BR': 'Nenhuma descrição fornecida.' },
  'jobDetail.hide': { en: 'Hide job', 'pt-BR': 'Ocultar vaga' },
  'jobDetail.unhide': { en: 'Show job', 'pt-BR': 'Mostrar vaga' },
  'jobDetail.hidden': { en: 'Job hidden from your list.', 'pt-BR': 'Vaga ocultada da sua lista.' },
  'jobDetail.unhidden': { en: 'Job is visible again.', 'pt-BR': 'Vaga visível novamente.' },
  'jobDetail.delete': { en: 'Delete', 'pt-BR': 'Excluir' },
  'jobDetail.deleteTitle': { en: 'Delete job?', 'pt-BR': 'Excluir vaga?' },
  'jobDetail.deleteMessage': {
    en: 'Delete "{title}" and all its applications? This cannot be undone.',
    'pt-BR': 'Excluir "{title}" e todas as suas candidaturas? Esta ação não pode ser desfeita.',
  },
  'jobDetail.deleted': { en: 'Job deleted.', 'pt-BR': 'Vaga excluída.' },

  // ---- Sources -------------------------------------------------------------
  'sources.title': { en: 'Job Sources', 'pt-BR': 'Fontes de Vagas' },
  'sources.addSource': { en: 'Add source', 'pt-BR': 'Adicionar fonte' },
  'sources.editSource': { en: 'Edit source', 'pt-BR': 'Editar fonte' },
  'sources.type.careerPage': { en: 'Career page', 'pt-BR': 'Página de carreiras' },
  'sources.type.aggregator': { en: 'Aggregator', 'pt-BR': 'Agregador' },
  'sources.type.rss': { en: 'RSS feed', 'pt-BR': 'Feed RSS' },
  'sources.type.discovery': { en: 'Discovery (search / ATS)', 'pt-BR': 'Descoberta (busca / ATS)' },
  'sources.adapter': { en: 'Adapter', 'pt-BR': 'Adaptador' },
  'sources.genericHtmlList': { en: 'Generic HTML list', 'pt-BR': 'Lista HTML genérica' },
  'sources.adapterConfig': { en: 'Adapter config (JSON)', 'pt-BR': 'Configuração do adaptador (JSON)' },
  'sources.adapterHintPrefix': { en: 'CSS selectors used by the generic HTML-list adapter. Optionally set', 'pt-BR': 'Seletores CSS usados pelo adaptador de lista HTML genérica. Opcionalmente, defina' },
  'sources.adapterHintSuffix': { en: 'to paginate through listing pages.', 'pt-BR': 'para paginar pelas páginas de listagem.' },
  'sources.provider': { en: 'Provider', 'pt-BR': 'Provedor' },
  'sources.loadingProviders': { en: 'Loading providers…', 'pt-BR': 'Carregando provedores…' },
  'sources.chooseProviderOption': { en: 'Choose a provider…', 'pt-BR': 'Escolha um provedor…' },
  'sources.apiKeyBadge': { en: 'API key', 'pt-BR': 'chave de API' },
  'sources.discoveryHint': {
    en: "ATS providers (ashby, greenhouse, lever, workable) fetch a board's public JSON feed. Search providers (google_cse, bing, brave, serpapi, brightdata) query a search API and then fetch each result page — serpapi/brightdata cover LinkedIn Jobs and Indeed via a paid, third-party key.",
    'pt-BR': 'Provedores ATS (ashby, greenhouse, lever, workable) buscam o feed JSON público de um quadro de vagas. Provedores de busca (google_cse, bing, brave, serpapi, brightdata) consultam uma API de busca e depois buscam cada página de resultados — serpapi/brightdata cobrem LinkedIn Jobs e Indeed por meio de uma chave paga de terceiros.',
  },
  'sources.needsApiKeyPrefix': { en: 'This provider needs an API key: save the source, then open its', 'pt-BR': 'Este provedor precisa de uma chave de API: salve a fonte e abra o painel' },
  'sources.needsApiKeyMiddle': { en: 'panel and choose', 'pt-BR': 'e escolha' },
  'sources.needsApiKeySuffix': { en: 'to store it encrypted.', 'pt-BR': 'para armazená-la criptografada.' },
  'sources.providerConfig': { en: 'Provider config (JSON)', 'pt-BR': 'Configuração do provedor (JSON)' },
  'sources.providerConfigHint': {
    en: 'Provider-specific settings. Search providers take query (and cx for Google, count for Bing/Brave), max_results and an optional detail_strategy (json_ld default, or selectors). ATS providers take the board identifier (org, board_token, company) and an optional company display name.',
    'pt-BR': 'Configurações específicas do provedor. Provedores de busca usam query (e cx para o Google, count para Bing/Brave), max_results e um detail_strategy opcional (json_ld por padrão ou selectors). Provedores ATS usam o identificador do quadro (org, board_token, company) e um nome de exibição company opcional.',
  },
  'sources.scrapingEthics': { en: 'Scraping ethics', 'pt-BR': 'Ética de coleta' },
  'sources.rateLimit': { en: 'Rate limit (seconds between requests)', 'pt-BR': 'Limite de requisições (segundos entre solicitações)' },
  'sources.rateLimitHint': { en: "Minimum delay enforced between requests to the source's domain. Higher values are more polite to the target site.", 'pt-BR': 'Atraso mínimo aplicado entre solicitações ao domínio da fonte. Valores maiores são mais educados com o site de destino.' },
  'sources.respectRobots': { en: 'Respect robots.txt', 'pt-BR': 'Respeitar o robots.txt' },
  'sources.respectRobotsHint': { en: "When enabled, the source is only fetched if its robots.txt allows it. Automated access may still violate the target's terms of service — review them before scraping.", 'pt-BR': 'Quando ativado, a fonte só é acessada se o robots.txt permitir. O acesso automatizado ainda pode violar os termos de serviço do destino — revise-os antes de coletar.' },
  'sources.saveChanges': { en: 'Save changes', 'pt-BR': 'Salvar alterações' },
  'sources.authenticationTitle': { en: 'Authentication — {name}', 'pt-BR': 'Autenticação — {name}' },
  'sources.authIntro': { en: 'For authenticated sources, paste a bearer token (Authorization header) or an API key (used by discovery providers). Credentials are encrypted at rest and never returned by the API. Note: automated access may violate the target site terms of service.', 'pt-BR': 'Para fontes autenticadas, cole um bearer token (cabeçalho Authorization) ou uma chave de API (usada por provedores de descoberta). As credenciais são criptografadas em repouso e nunca retornadas pela API. Observação: o acesso automatizado pode violar os termos de serviço do site de destino.' },
  'sources.authType': { en: 'Auth type', 'pt-BR': 'Tipo de autenticação' },
  'sources.authNone': { en: 'None (public)', 'pt-BR': 'Nenhuma (pública)' },
  'sources.authToken': { en: 'Bearer token', 'pt-BR': 'Bearer token' },
  'sources.authApiKey': { en: 'API key', 'pt-BR': 'Chave de API' },
  'sources.authTokenPlaceholder': { en: 'tok-…', 'pt-BR': 'tok-…' },
  'sources.authApiKeyPlaceholder': { en: 'search/ATS API key', 'pt-BR': 'chave de API de busca/ATS' },
  'sources.authApiKeyHint': { en: 'Used by discovery providers (Google CSE, Bing, Brave). Stored encrypted and never returned by the API.', 'pt-BR': 'Usada por provedores de descoberta (Google CSE, Bing, Brave). Armazenada criptografada e nunca retornada pela API.' },
  'sources.storedCredentialsPrefix': { en: 'Stored credentials: {type} (set ', 'pt-BR': 'Credenciais armazenadas: {type} (definida em ' },
  'sources.storedCredentialsSuffix': { en: '). Re-enter the value to replace them.', 'pt-BR': '). Insira o valor novamente para substituí-las.' },
  'sources.connectionOk': { en: 'Connection OK — the site responded with HTTP {status}.', 'pt-BR': 'Conexão OK — o site respondeu com HTTP {status}.' },
  'sources.connectionFailed': { en: 'Connection failed.', 'pt-BR': 'Falha na conexão.' },
  'sources.clearAuth': { en: 'Clear auth', 'pt-BR': 'Limpar autenticação' },
  'sources.testing': { en: 'Testing…', 'pt-BR': 'Testando…' },
  'sources.testConnection': { en: 'Test connection', 'pt-BR': 'Testar conexão' },
  'sources.saving': { en: 'Saving…', 'pt-BR': 'Salvando…' },
  'sources.sourceDeleted': { en: 'Source deleted.', 'pt-BR': 'Fonte excluída.' },
  'sources.sourceUpdated': { en: 'Source updated.', 'pt-BR': 'Fonte atualizada.' },
  'sources.sourceAdded': { en: 'Source added.', 'pt-BR': 'Fonte adicionada.' },
  'sources.authSaved': { en: 'Source authentication saved.', 'pt-BR': 'Autenticação da fonte salva.' },
  'sources.authOk': { en: 'Auth connection OK.', 'pt-BR': 'Conexão de autenticação OK.' },
  'sources.authFailed': { en: 'Auth test failed.', 'pt-BR': 'Falha no teste de autenticação.' },
  'sources.authFailedWith': { en: 'Auth test failed: {error}', 'pt-BR': 'Falha no teste de autenticação: {error}' },
  'sources.authCleared': { en: 'Source authentication cleared.', 'pt-BR': 'Autenticação da fonte limpa.' },
  'sources.deleteTitle': { en: 'Delete source?', 'pt-BR': 'Excluir fonte?' },
  'sources.deleteMessage': { en: 'Delete source "{name}"? Jobs already scraped from it will be kept.', 'pt-BR': 'Excluir a fonte "{name}"? As vagas já coletadas dela serão mantidas.' },
  'sources.keepSource': { en: 'Keep source', 'pt-BR': 'Manter fonte' },
  'sources.noSourcesYet': { en: 'No sources yet', 'pt-BR': 'Nenhuma fonte ainda' },
  'sources.noSourcesHint': { en: 'Add a career page, aggregator, or RSS feed to start collecting jobs.', 'pt-BR': 'Adicione uma página de carreiras, um agregador ou um feed RSS para começar a coletar vagas.' },
  'sources.addFirstSource': { en: 'Add your first source', 'pt-BR': 'Adicione sua primeira fonte' },
  'sources.lastScraped': { en: 'Last scraped', 'pt-BR': 'Última coleta' },

  // ---- Applications --------------------------------------------------------
  'applications.title': { en: 'Application Pipeline', 'pt-BR': 'Pipeline de Candidaturas' },
  'applications.total': { en: '{total} total', 'pt-BR': '{total} no total' },
  'applications.emptyTitle': { en: 'Your pipeline is empty', 'pt-BR': 'Seu pipeline está vazio' },
  'applications.emptyHint': { en: 'Open a job and press "Add to applications" to start tracking it here.', 'pt-BR': 'Abra uma vaga e clique em "Adicionar às candidaturas" para começar a acompanhá-la aqui.' },
  'applications.dropHere': { en: 'Drop here', 'pt-BR': 'Solte aqui' },
  'applications.viewPosting': { en: 'View posting', 'pt-BR': 'Ver publicação' },
  'applications.moveToStatus': { en: 'Move to status', 'pt-BR': 'Mover para o status' },
  'applications.removeTitle': { en: 'Remove application?', 'pt-BR': 'Remover candidatura?' },
  'applications.removeMessage': { en: 'Remove "{title}" from your pipeline? This cannot be undone.', 'pt-BR': 'Remover "{title}" do seu pipeline? Esta ação não pode ser desfeita.' },
  'applications.keepIt': { en: 'Keep it', 'pt-BR': 'Manter' },
  'applications.removed': { en: 'Application removed.', 'pt-BR': 'Candidatura removida.' },
  'applications.movedTo': { en: 'Moved to {status}.', 'pt-BR': 'Movida para {status}.' },

  // ---- CV editor -----------------------------------------------------------
  'cv.title': { en: 'Master CV', 'pt-BR': 'CV principal' },
  'cv.aria.editorMode': { en: 'CV editor mode', 'pt-BR': 'Modo do editor de CV' },
  'cv.edit': { en: 'Edit', 'pt-BR': 'Editar' },
  'cv.preview': { en: 'Preview', 'pt-BR': 'Pré-visualizar' },
  'cv.saveNewVersion': { en: 'Save as new version', 'pt-BR': 'Salvar como nova versão' },
  'cv.saving': { en: 'Saving…', 'pt-BR': 'Salvando…' },
  'cv.aria.editor': { en: 'Master CV editor', 'pt-BR': 'Editor do CV principal' },
  'cv.summary': { en: 'Summary', 'pt-BR': 'Resumo' },
  'cv.summaryPlaceholder': { en: 'Short professional summary', 'pt-BR': 'Resumo profissional curto' },
  'cv.aria.summary': { en: 'Professional summary', 'pt-BR': 'Resumo profissional' },
  'cv.skills': { en: 'Skills', 'pt-BR': 'Habilidades' },
  'cv.skillsPlaceholder': { en: 'python, fastapi, postgresql (comma separated)', 'pt-BR': 'python, fastapi, postgresql (separadas por vírgula)' },
  'cv.aria.skills': { en: 'Skills, comma separated', 'pt-BR': 'Habilidades, separadas por vírgula' },
  'cv.experience': { en: 'Experience', 'pt-BR': 'Experiência' },
  'cv.experienceItem': { en: 'Experience {n}', 'pt-BR': 'Experiência {n}' },
  'cv.start': { en: 'Start', 'pt-BR': 'Início' },
  'cv.end': { en: 'End', 'pt-BR': 'Fim' },
  'cv.bullets': { en: 'Bullet points (one per line)', 'pt-BR': 'Marcadores (um por linha)' },
  'cv.addExperience': { en: 'Add experience', 'pt-BR': 'Adicionar experiência' },
  'cv.education': { en: 'Education', 'pt-BR': 'Formação' },
  'cv.educationItem': { en: 'Education {n}', 'pt-BR': 'Formação {n}' },
  'cv.import': { en: 'Import PDF/DOCX', 'pt-BR': 'Importar PDF/DOCX' },
  'cv.imported': {
    en: 'CV imported — review it, then save as a new version.',
    'pt-BR': 'CV importado — revise e salve como uma nova versão.',
  },
  'cv.importedToast': { en: 'CV imported from file.', 'pt-BR': 'CV importado do arquivo.' },
  'cv.importing': { en: 'Importing…', 'pt-BR': 'Importando…' },
  'cv.institution': { en: 'Institution', 'pt-BR': 'Instituição' },
  'cv.degree': { en: 'Degree', 'pt-BR': 'Titulação' },
  'cv.year': { en: 'Year', 'pt-BR': 'Ano' },
  'cv.addEducation': { en: 'Add education', 'pt-BR': 'Adicionar formação' },
  'cv.projects': { en: 'Projects', 'pt-BR': 'Projetos' },
  'cv.projectItem': { en: 'Project {n}', 'pt-BR': 'Projeto {n}' },
  'cv.link': { en: 'Link', 'pt-BR': 'Link' },
  'cv.addProject': { en: 'Add project', 'pt-BR': 'Adicionar projeto' },
  'cv.versionHistory': { en: 'Version history', 'pt-BR': 'Histórico de versões' },
  'cv.noVersions': { en: 'No versions saved yet.', 'pt-BR': 'Nenhuma versão salva ainda.' },
  'cv.current': { en: 'current', 'pt-BR': 'atual' },
  'cv.tailoredCvs': { en: 'Tailored CVs', 'pt-BR': 'CVs personalizados' },
  'cv.noTailored': { en: 'No tailored CVs yet — use "Tailor CV" on a job.', 'pt-BR': 'Nenhum CV personalizado ainda — use "Personalizar CV" em uma vaga.' },
  'cv.pdf': { en: 'PDF', 'pt-BR': 'PDF' },
  'cv.savedAs': { en: 'Saved as {label}.', 'pt-BR': 'Salvo como {label}.' },
  'cv.savedAsToast': { en: 'Master CV saved as {label}.', 'pt-BR': 'CV principal salvo como {label}.' },
  'cv.exportPdf': { en: 'Download PDF', 'pt-BR': 'Baixar PDF' },
  'cv.exporting': { en: 'Exporting…', 'pt-BR': 'Exportando…' },
  'cv.pdfExported': { en: 'PDF exported.', 'pt-BR': 'PDF exportado.' },
  'cv.editTailored': { en: 'Edit tailored CV', 'pt-BR': 'Editar CV personalizado' },
  'cv.editingTailored': {
    en: 'Loaded {job} into the editor — edit it, then export or save as a new version.',
    'pt-BR': '{job} carregado no editor — edite e depois exporte ou salve como nova versão.',
  },
  'cv.editingTailoredToast': { en: 'Tailored CV loaded for editing.', 'pt-BR': 'CV personalizado carregado para edição.' },

  // ---- Alerts --------------------------------------------------------------
  'alerts.title': { en: 'Job Alerts', 'pt-BR': 'Alertas de Vagas' },
  'alerts.newAlert': { en: 'New alert', 'pt-BR': 'Novo alerta' },
  'alerts.editAlert': { en: 'Edit alert', 'pt-BR': 'Editar alerta' },
  'alerts.keywords': { en: 'Keywords (comma separated)', 'pt-BR': 'Palavras-chave (separadas por vírgula)' },
  'alerts.companies': { en: 'Companies (comma separated)', 'pt-BR': 'Empresas (separadas por vírgula)' },
  'alerts.tags': { en: 'Tags (comma separated)', 'pt-BR': 'Tags (separadas por vírgula)' },
  'alerts.minYears': { en: 'Min years of experience', 'pt-BR': 'Anos mínimos de experiência' },
  'alerts.channels': { en: 'Channels (comma separated: in_app, email)', 'pt-BR': 'Canais (separados por vírgula: in_app, email)' },
  'alerts.remoteOnly': { en: 'Remote-only', 'pt-BR': 'Somente remoto' },
  'alerts.active': { en: 'Active', 'pt-BR': 'Ativa' },
  'alerts.saveChanges': { en: 'Save changes', 'pt-BR': 'Salvar alterações' },
  'alerts.createAlert': { en: 'Create alert', 'pt-BR': 'Criar alerta' },
  'alerts.loading': { en: 'Loading alerts…', 'pt-BR': 'Carregando alertas…' },
  'alerts.noRules': { en: 'No alert rules yet', 'pt-BR': 'Nenhuma regra de alerta ainda' },
  'alerts.noRulesHint': { en: 'Create one to get notified about new matching jobs.', 'pt-BR': 'Crie uma para ser notificado sobre novas vagas correspondentes.' },
  'alerts.createOne': { en: 'Create an alert', 'pt-BR': 'Criar um alerta' },
  'alerts.tableKeywords': { en: 'Keywords', 'pt-BR': 'Palavras-chave' },
  'alerts.tableCompanies': { en: 'Companies', 'pt-BR': 'Empresas' },
  'alerts.tableRemote': { en: 'Remote', 'pt-BR': 'Remoto' },
  'alerts.tableMinYears': { en: 'Min years', 'pt-BR': 'Anos mín.' },
  'alerts.tableChannels': { en: 'Channels', 'pt-BR': 'Canais' },
  'alerts.tableStatus': { en: 'Status', 'pt-BR': 'Status' },
  'alerts.paused': { en: 'Paused', 'pt-BR': 'Pausada' },
  'alerts.updated': { en: 'Alert updated.', 'pt-BR': 'Alerta atualizado.' },
  'alerts.created': { en: 'Alert created.', 'pt-BR': 'Alerta criado.' },
  'alerts.pausedToast': { en: 'Alert paused.', 'pt-BR': 'Alerta pausado.' },
  'alerts.activatedToast': { en: 'Alert activated.', 'pt-BR': 'Alerta ativado.' },
  'alerts.deletedToast': { en: 'Alert deleted.', 'pt-BR': 'Alerta excluído.' },
  'alerts.deleteTitle': { en: 'Delete alert?', 'pt-BR': 'Excluir alerta?' },
  'alerts.deleteMessage': { en: 'Delete alert "{name}"? You will stop receiving matching job notifications.', 'pt-BR': 'Excluir o alerta "{name}"? Você deixará de receber notificações de vagas correspondentes.' },
  'alerts.keepAlert': { en: 'Keep alert', 'pt-BR': 'Manter alerta' },

  // ---- Notifications -------------------------------------------------------
  'notifications.title': { en: 'Notifications', 'pt-BR': 'Notificações' },
  'notifications.markAllRead': { en: 'Mark all read', 'pt-BR': 'Marcar todas como lidas' },
  'notifications.unread': { en: '{count} unread', 'pt-BR': '{count} não lidas' },
  'notifications.total': { en: '{count} total', 'pt-BR': '{count} no total' },
  'notifications.emptyTitle': { en: "You're all caught up", 'pt-BR': 'Você está em dia' },
  'notifications.emptyHint': { en: "New matching jobs will appear here as soon as they're scraped.", 'pt-BR': 'Novas vagas correspondentes aparecerão aqui assim que forem coletadas.' },
  'notifications.markRead': { en: 'Mark read', 'pt-BR': 'Marcar como lida' },
  'notifications.allReadToast': { en: 'All notifications marked as read.', 'pt-BR': 'Todas as notificações marcadas como lidas.' },

  // ---- Admin ---------------------------------------------------------------
  'admin.title': { en: 'Admin', 'pt-BR': 'Admin' },
  'admin.refresh': { en: 'Refresh', 'pt-BR': 'Atualizar' },
  'admin.aria.sections': { en: 'Admin sections', 'pt-BR': 'Seções de administração' },
  'admin.tabs.overview': { en: 'Overview', 'pt-BR': 'Visão geral' },
  'admin.tabs.sources': { en: 'Sources', 'pt-BR': 'Fontes' },
  'admin.tabs.quality': { en: 'Quality', 'pt-BR': 'Qualidade' },
  'admin.tabs.dlq': { en: 'Dead-Letter Queue', 'pt-BR': 'Fila de Mensagens Mortas' },
  'admin.tabs.audit': { en: 'Audit Log', 'pt-BR': 'Log de Auditoria' },
  'admin.tabs.llm': { en: 'LLM', 'pt-BR': 'LLM' },
  'admin.refreshing': { en: 'Refreshing data…', 'pt-BR': 'Atualizando dados…' },
  'admin.statSources': { en: 'Sources', 'pt-BR': 'Fontes' },
  'admin.statJobs': { en: 'Jobs', 'pt-BR': 'Vagas' },
  'admin.statJobs24h': { en: 'Jobs (24h)', 'pt-BR': 'Vagas (24h)' },
  'admin.statFailedRuns': { en: 'Failed runs', 'pt-BR': 'Execuções com falha' },
  'admin.statTotalRuns': { en: 'Total runs', 'pt-BR': 'Total de execuções' },
  'admin.sourceHealth': { en: 'Source Health', 'pt-BR': 'Saúde das Fontes' },
  'admin.lastScraped': { en: 'Last scraped', 'pt-BR': 'Última coleta' },
  'admin.action': { en: 'Action', 'pt-BR': 'Ação' },
  'admin.never': { en: 'never', 'pt-BR': 'nunca' },
  'admin.scrapeNow': { en: 'Scrape now', 'pt-BR': 'Coletar agora' },
  'admin.dlqTitle': { en: 'Dead-Letter Queue (failed scrape runs)', 'pt-BR': 'Fila de Mensagens Mortas (execuções de coleta com falha)' },
  'admin.noFailedRuns': { en: 'No failed runs', 'pt-BR': 'Nenhuma execução com falha' },
  'admin.noFailedRunsHint': { en: 'Everything is healthy — nothing to replay.', 'pt-BR': 'Tudo saudável — nada para reproduzir.' },
  'admin.started': { en: 'Started', 'pt-BR': 'Iniciada' },
  'admin.errorCol': { en: 'Error', 'pt-BR': 'Erro' },
  'admin.jobsCol': { en: 'Jobs', 'pt-BR': 'Vagas' },
  'admin.replay': { en: 'Replay', 'pt-BR': 'Reproduzir' },
  'admin.dataQuality': { en: 'Data Quality', 'pt-BR': 'Qualidade dos Dados' },
  'admin.jobsAssessed': { en: 'Jobs assessed', 'pt-BR': 'Vagas avaliadas' },
  'admin.avgCompleteness': { en: 'Avg completeness', 'pt-BR': 'Completude média' },
  'admin.duplicates': { en: 'Duplicates', 'pt-BR': 'Duplicadas' },
  'admin.normalization': { en: 'Normalization', 'pt-BR': 'Normalização' },
  'admin.withIssues': { en: 'With issues', 'pt-BR': 'Com problemas' },
  'admin.sourceCol': { en: 'Source', 'pt-BR': 'Fonte' },
  'admin.titleCol': { en: 'Title', 'pt-BR': 'Título' },
  'admin.companyCol': { en: 'Company', 'pt-BR': 'Empresa' },
  'admin.completeness': { en: 'Completeness', 'pt-BR': 'Completude' },
  'admin.normalized': { en: 'Normalized', 'pt-BR': 'Normalizado' },
  'admin.issues': { en: 'Issues', 'pt-BR': 'Problemas' },
  'admin.flaggedOnly': { en: 'Flagged only (duplicates / issues)', 'pt-BR': 'Somente sinalizadas (duplicadas / problemas)' },
  'admin.noAssessedJobs': { en: 'No assessed jobs yet — trigger a scrape to generate quality data.', 'pt-BR': 'Nenhuma vaga avaliada ainda — inicie uma coleta para gerar dados de qualidade.' },
  'admin.auditLog': { en: 'Audit Log', 'pt-BR': 'Log de Auditoria' },
  'admin.allActions': { en: 'All actions', 'pt-BR': 'Todas as ações' },
  'admin.allEntityTypes': { en: 'All entity types', 'pt-BR': 'Todos os tipos de entidade' },
  'admin.fromDate': { en: 'From date', 'pt-BR': 'Data inicial' },
  'admin.toDate': { en: 'To date', 'pt-BR': 'Data final' },
  'admin.noAuditEntries': { en: 'No audit entries match the filters.', 'pt-BR': 'Nenhuma entrada de auditoria corresponde aos filtros.' },
  'admin.timestamp': { en: 'Timestamp', 'pt-BR': 'Data/hora' },
  'admin.user': { en: 'User', 'pt-BR': 'Usuário' },
  'admin.actionCol': { en: 'Action', 'pt-BR': 'Ação' },
  'admin.entity': { en: 'Entity', 'pt-BR': 'Entidade' },
  'admin.details': { en: 'Details', 'pt-BR': 'Detalhes' },
  'admin.hide': { en: 'Hide', 'pt-BR': 'Ocultar' },
  'admin.llmTitle': { en: 'LLM (CV tailoring)', 'pt-BR': 'LLM (personalização de CV)' },
  'admin.llmIntro': { en: 'Configure an OpenAI-compatible API used to rephrase CV bullet points during tailoring. Leave the API key blank to keep the currently stored key.', 'pt-BR': 'Configure uma API compatível com OpenAI usada para reformular os marcadores do CV durante a personalização. Deixe a chave de API em branco para manter a chave atualmente armazenada.' },
  'admin.enableLlm': { en: 'Enable LLM rephrasing', 'pt-BR': 'Ativar reformulação com LLM' },
  'admin.baseUrl': { en: 'Base URL', 'pt-BR': 'URL base' },
  'admin.model': { en: 'Model', 'pt-BR': 'Modelo' },
  'admin.apiKey': { en: 'API key', 'pt-BR': 'Chave de API' },
  'admin.stored': { en: 'stored:', 'pt-BR': 'armazenada:' },
  'admin.notSet': { en: 'not set', 'pt-BR': 'não definida' },
  'admin.connectedOk': { en: 'Connected successfully.', 'pt-BR': 'Conectado com sucesso.' },
  'admin.connectionFailed': { en: 'Connection failed.', 'pt-BR': 'Falha na conexão.' },
  'admin.reset': { en: 'Reset', 'pt-BR': 'Redefinir' },
  'admin.testing': { en: 'Testing…', 'pt-BR': 'Testando…' },
  'admin.testConnection': { en: 'Test connection', 'pt-BR': 'Testar conexão' },
  'admin.saving': { en: 'Saving…', 'pt-BR': 'Salvando…' },
  'admin.save': { en: 'Save', 'pt-BR': 'Salvar' },
  'admin.llmSaved': { en: 'LLM settings saved.', 'pt-BR': 'Configurações do LLM salvas.' },
  'admin.llmOk': { en: 'LLM connection OK.', 'pt-BR': 'Conexão do LLM OK.' },
  'admin.llmFailed': { en: 'LLM test failed.', 'pt-BR': 'Falha no teste do LLM.' },
  'admin.llmFailedWith': { en: 'LLM test failed: {error}', 'pt-BR': 'Falha no teste do LLM: {error}' },
  'admin.scrapeTriggered': { en: 'Scrape triggered.', 'pt-BR': 'Coleta iniciada.' },
  'admin.runReplayed': { en: 'Run replayed.', 'pt-BR': 'Execução reproduzida.' },

  // ---- Onboarding ----------------------------------------------------------
  'onboarding.welcome': { en: 'Welcome to PudimJobs 👋', 'pt-BR': 'Bem-vindo ao PudimJobs 👋' },
  'onboarding.intro': { en: "Here's how to go from job boards to your first offer in three steps.", 'pt-BR': 'Veja como ir dos quadros de vagas até a sua primeira oferta em três passos.' },
  'onboarding.step1.title': { en: 'Add a job source', 'pt-BR': 'Adicione uma fonte de vagas' },
  'onboarding.step1.description': { en: 'Connect a career page, aggregator, or RSS feed so new jobs are scraped automatically.', 'pt-BR': 'Conecte uma página de carreiras, um agregador ou um feed RSS para que novas vagas sejam coletadas automaticamente.' },
  'onboarding.step1.cta': { en: 'Add sources', 'pt-BR': 'Adicionar fontes' },
  'onboarding.step2.title': { en: 'Create your master CV', 'pt-BR': 'Crie seu CV principal' },
  'onboarding.step2.description': { en: 'Store your summary, skills, experience, and education once — then tailor it per job.', 'pt-BR': 'Armazene seu resumo, habilidades, experiência e formação uma vez — depois personalize por vaga.' },
  'onboarding.step2.cta': { en: 'Edit CV', 'pt-BR': 'Editar CV' },
  'onboarding.step3.title': { en: 'Track applications', 'pt-BR': 'Acompanhe as candidaturas' },
  'onboarding.step3.description': { en: 'Move jobs through Saved → Applied → Interview → Offer and stay on top of your pipeline.', 'pt-BR': 'Mova as vagas por Salva → Candidatada → Entrevista → Oferta e mantenha o controle do seu pipeline.' },
  'onboarding.step3.cta': { en: 'Open pipeline', 'pt-BR': 'Abrir pipeline' },
  'onboarding.dismiss': { en: 'Got it — hide this', 'pt-BR': 'Entendi — ocultar isto' },

  // ---- Confirm dialog ------------------------------------------------------
  'confirm.areYouSure': { en: 'Are you sure?', 'pt-BR': 'Tem certeza?' },
  'confirm.confirm': { en: 'Confirm', 'pt-BR': 'Confirmar' },
  'confirm.cancel': { en: 'Cancel', 'pt-BR': 'Cancelar' },

  // ---- Toasts --------------------------------------------------------------
  'toast.dismiss': { en: 'Dismiss notification', 'pt-BR': 'Dispensar notificação' },

  // ---- CV preview ----------------------------------------------------------
  'cvPreview.summaryEmpty': { en: 'Your professional summary appears here.', 'pt-BR': 'Seu resumo profissional aparecerá aqui.' },
  'cvPreview.skills': { en: 'Skills', 'pt-BR': 'Habilidades' },
  'cvPreview.experience': { en: 'Experience', 'pt-BR': 'Experiência' },
  'cvPreview.education': { en: 'Education', 'pt-BR': 'Formação' },
  'cvPreview.projects': { en: 'Projects', 'pt-BR': 'Projetos' },

  // ---- Months (short form, used by the CV preview date formatter) ----------
  'months.1': { en: 'Jan', 'pt-BR': 'jan' },
  'months.2': { en: 'Feb', 'pt-BR': 'fev' },
  'months.3': { en: 'Mar', 'pt-BR': 'mar' },
  'months.4': { en: 'Apr', 'pt-BR': 'abr' },
  'months.5': { en: 'May', 'pt-BR': 'mai' },
  'months.6': { en: 'Jun', 'pt-BR': 'jun' },
  'months.7': { en: 'Jul', 'pt-BR': 'jul' },
  'months.8': { en: 'Aug', 'pt-BR': 'ago' },
  'months.9': { en: 'Sep', 'pt-BR': 'set' },
  'months.10': { en: 'Oct', 'pt-BR': 'out' },
  'months.11': { en: 'Nov', 'pt-BR': 'nov' },
  'months.12': { en: 'Dec', 'pt-BR': 'dez' },

  // ---- Errors / failures ---------------------------------------------------
  'errors.failedLoadJobs': { en: 'Failed to load jobs', 'pt-BR': 'Falha ao carregar as vagas' },
  'errors.failedCreateJob': { en: 'Failed to create job', 'pt-BR': 'Falha ao criar a vaga' },
  'errors.failedHideJob': { en: 'Failed to update job visibility', 'pt-BR': 'Falha ao atualizar a visibilidade da vaga' },
  'errors.failedDeleteJob': { en: 'Failed to delete job', 'pt-BR': 'Falha ao excluir a vaga' },
  'errors.failedLoadJob': { en: 'Failed to load job', 'pt-BR': 'Falha ao carregar a vaga' },
  'errors.failedEnqueueParsing': { en: 'Failed to enqueue parsing', 'pt-BR': 'Falha ao enfileirar a análise' },
  'errors.failedLoadSources': { en: 'Failed to load sources', 'pt-BR': 'Falha ao carregar as fontes' },
  'errors.failedSaveSource': { en: 'Failed to save source', 'pt-BR': 'Falha ao salvar a fonte' },
  'errors.failedDeleteSource': { en: 'Failed to delete source', 'pt-BR': 'Falha ao excluir a fonte' },
  'errors.failedSaveAuth': { en: 'Failed to save source authentication', 'pt-BR': 'Falha ao salvar a autenticação da fonte' },
  'errors.failedRunAuthTest': { en: 'Failed to run auth test', 'pt-BR': 'Falha ao executar o teste de autenticação' },
  'errors.failedClearAuth': { en: 'Failed to clear source authentication', 'pt-BR': 'Falha ao limpar a autenticação da fonte' },
  'errors.invalidAggregatorJson': { en: 'Invalid aggregator config JSON', 'pt-BR': 'JSON de configuração do agregador inválido' },
  'errors.chooseProvider': { en: 'Choose a discovery provider', 'pt-BR': 'Escolha um provedor de descoberta' },
  'errors.invalidDiscoveryJson': { en: 'Invalid discovery config JSON', 'pt-BR': 'JSON de configuração de descoberta inválido' },
  'errors.failedLoadApplications': { en: 'Failed to load applications', 'pt-BR': 'Falha ao carregar as candidaturas' },
  'errors.failedMoveApplication': { en: 'Failed to move application', 'pt-BR': 'Falha ao mover a candidatura' },
  'errors.failedUpdateStatus': { en: 'Failed to update status', 'pt-BR': 'Falha ao atualizar o status' },
  'errors.failedDeleteApplication': { en: 'Failed to delete application', 'pt-BR': 'Falha ao excluir a candidatura' },
  'errors.failedLoadCV': { en: 'Failed to load CV', 'pt-BR': 'Falha ao carregar o CV' },
  'errors.failedDownloadPdf': { en: 'Failed to download PDF', 'pt-BR': 'Falha ao baixar o PDF' },
  'errors.failedExportPdf': { en: 'Failed to export PDF', 'pt-BR': 'Falha ao exportar o PDF' },
  'errors.failedSaveCV': { en: 'Failed to save CV', 'pt-BR': 'Falha ao salvar o CV' },
  'errors.failedParseCV': {
    en: 'Failed to parse the CV file',
    'pt-BR': 'Falha ao analisar o arquivo do CV',
  },
  'errors.unsupportedCvFile': {
    en: 'Unsupported file. Upload a PDF or DOCX.',
    'pt-BR': 'Arquivo não suportado. Envie um PDF ou DOCX.',
  },
  'errors.failedLoadAlerts': { en: 'Failed to load alert rules', 'pt-BR': 'Falha ao carregar as regras de alerta' },
  'errors.failedSaveAlert': { en: 'Failed to save alert rule', 'pt-BR': 'Falha ao salvar a regra de alerta' },
  'errors.failedUpdateRule': { en: 'Failed to update rule', 'pt-BR': 'Falha ao atualizar a regra' },
  'errors.failedDeleteAlert': { en: 'Failed to delete alert rule', 'pt-BR': 'Falha ao excluir a regra de alerta' },
  'errors.failedLoadNotifications': { en: 'Failed to load notifications', 'pt-BR': 'Falha ao carregar as notificações' },
  'errors.failedUpdateNotification': { en: 'Failed to update notification', 'pt-BR': 'Falha ao atualizar a notificação' },
  'errors.failedUpdateNotifications': { en: 'Failed to update notifications', 'pt-BR': 'Falha ao atualizar as notificações' },
  'errors.failedLoadStats': { en: 'Failed to load stats', 'pt-BR': 'Falha ao carregar as estatísticas' },
  'errors.failedLoadSourceHealth': { en: 'Failed to load source health', 'pt-BR': 'Falha ao carregar a saúde das fontes' },
  'errors.failedLoadDlq': { en: 'Failed to load DLQ', 'pt-BR': 'Falha ao carregar a fila de mensagens mortas' },
  'errors.failedLoadQuality': { en: 'Failed to load quality overview', 'pt-BR': 'Falha ao carregar o resumo de qualidade' },
  'errors.failedLoadQualityJobs': { en: 'Failed to load quality jobs', 'pt-BR': 'Falha ao carregar as vagas de qualidade' },
  'errors.failedLoadAudit': { en: 'Failed to load audit log', 'pt-BR': 'Falha ao carregar o log de auditoria' },
  'errors.failedTriggerScrape': { en: 'Failed to trigger scrape', 'pt-BR': 'Falha ao iniciar a coleta' },
  'errors.failedReplay': { en: 'Failed to replay run', 'pt-BR': 'Falha ao reproduzir a execução' },
  'errors.failedLoadLlm': { en: 'Failed to load LLM settings', 'pt-BR': 'Falha ao carregar as configurações do LLM' },
  'errors.failedSaveLlm': { en: 'Failed to save LLM settings', 'pt-BR': 'Falha ao salvar as configurações do LLM' },
  'errors.failedRunLlmTest': { en: 'Failed to run LLM test', 'pt-BR': 'Falha ao executar o teste do LLM' },
};

@Injectable({ providedIn: 'root' })
export class I18nService {
  readonly lang = signal<Language>(this.loadInitial());

  constructor() {
    // Apply the persisted/browser language to <html>, title and meta before the
    // first route paints (mirrors ThemeService's early-instantiation pattern).
    this.apply(this.lang());
  }

  get current(): Language {
    return this.lang();
  }

  /**
   * Returns the translation for `key` in the active language, interpolating any
   * `{placeholder}` tokens from `params`. Falls back to the key itself when the
   * dictionary has no entry for it.
   */
  t(key: string, params?: Record<string, string | number | null | undefined>): string {
    const entry = DICTIONARY[key];
    let value = entry ? entry[this.lang()] : key;
    if (params) {
      value = value.replace(/\{(\w+)\}/g, (match, name: string) =>
        params[name] !== undefined ? String(params[name]) : match
      );
    }
    return value;
  }

  /** Switches between English and Brazilian Portuguese. */
  toggle(): Language {
    this.setLanguage(this.lang() === 'en' ? 'pt-BR' : 'en');
    return this.lang();
  }

  setLanguage(lang: Language): void {
    this.lang.set(lang);
    localStorage.setItem(STORAGE_KEY, lang);
    this.apply(lang);
  }

  /** Keeps <html lang>, the document title and the meta description in sync. */
  private apply(lang: Language): void {
    document.documentElement.lang = lang;
    document.title = this.t('app.title');
    const meta = document.querySelector<HTMLMetaElement>('meta[name="description"]');
    if (meta) {
      meta.content = this.t('app.description');
    }
  }

  private loadInitial(): Language {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === 'en' || stored === 'pt-BR') {
      return stored;
    }
    return navigator.language.toLowerCase().startsWith('pt') ? 'pt-BR' : 'en';
  }
}
