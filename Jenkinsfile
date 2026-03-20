// Jenkinsfile — AI QA Framework v2
// Supports: autonomy levels, parallel agents, API testing, story generation,
//           signal-gated bugs, LLM cache, self-healing mode

pipeline {

    agent any

    parameters {
	
	        // Add this parameter at the beginning of your parameters block
        booleanParam(
            name: 'REBUILD_LAST',
            defaultValue: false,
            description: 'Check to rebuild with same parameters as last successful build'
        )
        

        // ── Target ────────────────────────────────────────────────────────────
        string(
            name:         'TARGET_URLS',
            defaultValue: 'https://www.saucedemo.com,https://reqres.in/',
            description:  'Comma-separated URLs to test (no spaces)'
        )

        // ── Autonomy level ────────────────────────────────────────────────────
        choice(
            name:         'AUTONOMY_LEVEL',
            choices:      ['3', '2', '1'],
            description:  '1=Manual (stories only), 2=Semi-Auto (recommended), 3=Full Auto'
        )

        // ── Browser ───────────────────────────────────────────────────────────
        choice(
            name:         'BROWSER',
            choices:      ['chromium', 'firefox', 'webkit'],
            description:  'Browser engine'
        )
        string(
            name:         'MAX_STEPS',
            defaultValue: '3',
            description:  'AI exploration steps per page'
        )
        string(
            name:         'MAX_CRAWL_PAGES',
            defaultValue: '2',
            description:  'Max pages to crawl per URL'
        )
        string(
            name:         'MAX_CRAWL_DEPTH',
            defaultValue: '1',
            description:  'Max link depth'
        )
        string(
            name:         'PARALLEL_AGENTS',
            defaultValue: '1',
            description:  'URLs tested simultaneously (max 2 on 16GB RAM)'
        )

        // ── AI / Ollama ───────────────────────────────────────────────────────
        string(
            name:         'OLLAMA_MODEL',
            defaultValue: 'llama3:latest',
            description:  'Ollama model — must match output of: ollama list'
        )
        choice(
            name:         'STEALTH_MODE',
            choices:      ['true', 'false'],
            description:  'Stealth browser (bypasses bot detection)'
        )

        // ── Login ─────────────────────────────────────────────────────────────
        string(
            name:         'LOGIN_EMAIL',
            defaultValue: 'standard_user',
            description:  'Login email/username (blank if no login needed)'
        )
        password(
            name:         'LOGIN_PASSWORD',
            defaultValue: 'secret_sauce',
            description:  'Login password (stored as Jenkins secret)'
        )

        // ── Feature flags ─────────────────────────────────────────────────────
        booleanParam(
            name:         'STORY_ENABLED',
            defaultValue: true,
            description:  'Auto-generate regression stories from discovered TCs'
        )
        booleanParam(
            name:         'API_TESTING',
            defaultValue: true,
            description:  'Test API endpoints captured during browser crawl'
        )
        string(
            name:         'API_TIMEOUT_MS',
            defaultValue: '3000',
            description:  'API response time budget in ms'
        )
        choice(
            name:         'SELF_HEALING',
            choices:      ['true', 'false'],
            description:  'true=exploratory (5 fallbacks), false=strict (exact match)'
        )
        booleanParam(
            name:         'CACHE_ENABLED',
            defaultValue: true,
            description:  'Cache LLM responses — same page skips Ollama call for 24h'
        )
        choice(
            name:         'LOG_LEVEL',
            choices:      ['INFO', 'QUIET', 'DEBUG'],
            description:  'Logging verbosity: QUIET=only results, INFO=default, DEBUG=verbose'
        )
    }

    environment {
        // ── From parameters ───────────────────────────────────────────────────
        TARGET_URLS             = "${params.TARGET_URLS}"
        AUTONOMY_LEVEL          = "${params.AUTONOMY_LEVEL}"
        BROWSER                 = "${params.BROWSER}"
        MAX_STEPS               = "${params.MAX_STEPS}"
        MAX_CRAWL_PAGES         = "${params.MAX_CRAWL_PAGES}"
        MAX_CRAWL_DEPTH         = "${params.MAX_CRAWL_DEPTH}"
        PARALLEL_AGENTS         = "${params.PARALLEL_AGENTS}"
        OLLAMA_MODEL            = "${params.OLLAMA_MODEL}"
        STEALTH_MODE            = "${params.STEALTH_MODE}"
        LOGIN_EMAIL             = "${params.LOGIN_EMAIL}"
        LOGIN_PASSWORD          = "${params.LOGIN_PASSWORD}"
        STORY_ENABLED           = "${params.STORY_ENABLED}"
        API_TESTING             = "${params.API_TESTING}"
        API_TIMEOUT_MS          = "${params.API_TIMEOUT_MS}"
        SELF_HEALING            = "${params.SELF_HEALING}"
        CACHE_ENABLED           = "${params.CACHE_ENABLED}"
        LOG_LEVEL               = "${params.LOG_LEVEL}"

        // ── Fixed CI values (from config.txt) ─────────────────────────────────
        HEADLESS                = "true"
        PAGE_TIMEOUT            = "60000"
        USER_AGENT              = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        VIEWPORT_WIDTH          = "1280"
        VIEWPORT_HEIGHT         = "800"
        LOCALE                  = "en-US"
        TIMEZONE                = "America/New_York"
        
        // ── Ollama Configuration ──────────────────────────────────────────────
        OLLAMA_HOST             = "http://localhost:11434"
        OLLAMA_READ_TIMEOUT     = "400"
        OLLAMA_CONNECT_TIMEOUT  = "5"
        OLLAMA_RETRIES          = "1"
        
        // ── Cache Configuration ───────────────────────────────────────────────
        CACHE_TTL_HOURS         = "24"
        
        // ── Reporting Paths ───────────────────────────────────────────────────
        ALLURE_RESULTS_DIR      = "allure-results"
        ALLURE_REPORT_DIR       = "allure-report"
        BUG_REPORTS_DIR         = "bug_reports"
        SCREENSHOTS_DIR         = "screenshots"
        TC_FILE                 = "generated_test_cases.xlsx"
        
        // ── Python Environment ────────────────────────────────────────────────
        PYTHONUNBUFFERED        = "1"
        PYTHONIOENCODING        = "utf-8"
    }

    options {
        buildDiscarder(logRotator(numToKeepStr: '10'))
        timeout(time: 3, unit: 'HOURS')
        timestamps()
        disableConcurrentBuilds()
    }

    stages {

        stage('Checkout') {
            steps {
                echo "Checking out source..."
                checkout scm
                script {
                    if (isUnix()) { sh 'git log --oneline -3' }
                    else          { bat 'git log --oneline -3' }
                }
            }
        }

        stage('Setup Python') {
            steps {
                script {
                    if (isUnix()) {
                        sh '''
                            python3 -m venv venv
                            . venv/bin/activate
                            pip install --upgrade pip --quiet
                            pip install -r requirements.txt --quiet
                            python -m playwright install chromium
                        '''
                    } else {
                        bat 'python -m venv venv'
                        bat 'venv\\Scripts\\python.exe -m pip install --upgrade pip --quiet'
                        bat 'venv\\Scripts\\python.exe -m pip install -r requirements.txt --quiet'
                        bat 'venv\\Scripts\\python.exe -m playwright install chromium'
                    }
                }
            }
        }

        stage('Pre-flight') {
            steps {
                script {
                    echo "========================================"
                    echo "AI QA Framework Configuration"
                    echo "========================================"
                    echo "Autonomy level    : ${params.AUTONOMY_LEVEL} (3=Full Auto)"
                    echo "Target URLs       : ${params.TARGET_URLS}"
                    echo "Parallel agents   : ${params.PARALLEL_AGENTS}"
                    echo "API testing       : ${params.API_TESTING}"
                    echo "Story generation  : ${params.STORY_ENABLED}"
                    echo "Ollama model      : ${params.OLLAMA_MODEL}"
                    echo "Log level         : ${params.LOG_LEVEL}"
                    echo "Self-healing      : ${params.SELF_HEALING}"
                    echo "Cache enabled     : ${params.CACHE_ENABLED}"
                    echo "Stealth mode      : ${params.STEALTH_MODE}"
                    echo "Browser           : ${env.BROWSER}"
                    echo "Headless          : ${env.HEADLESS}"
                    echo "========================================"
                    
                    // Check Ollama availability
                    if (isUnix()) {
                        sh 'curl -sf http://localhost:11434/api/tags || echo "WARNING: Ollama not responding"'
                    } else {
                        bat 'curl -sf http://localhost:11434/api/tags || echo WARNING: Ollama not responding'
                    }
                }
            }
        }

        stage('Run AI Tests') {
            steps {
                script {
                    // Test files to run
                    def test_files = 'run_agents.py tests/test_agent_results.py tests/test_api_results.py tests/test_bugs.py tests/test_generated_tcs.py tests/test_user_stories.py'
                    def allure_args = '--alluredir=allure-results --clean-alluredir -v --tb=short'
                    def warnings = '-W ignore::urllib3.exceptions.InsecureRequestWarning'
                    
                    // Build pytest command without duplicate pytest
                    def pytest_cmd = "${test_files} ${allure_args} ${warnings}"

                    if (isUnix()) {
                        sh """
                            . venv/bin/activate
                            pytest ${pytest_cmd}
                        """
                    } else {
                        bat "venv\\\\Scripts\\\\python.exe -m pytest ${pytest_cmd} > pytest_output.txt 2>&1"
                        bat 'type pytest_output.txt'
                    }
                }
            }
        }

        stage('Archive Artifacts') {
            steps {
                archiveArtifacts artifacts: 'screenshots/**/*.png',         allowEmptyArchive: true
                archiveArtifacts artifacts: 'bug_reports/**/*.json',        allowEmptyArchive: true
                archiveArtifacts artifacts: 'generated_test_cases/**/*',    allowEmptyArchive: true
                archiveArtifacts artifacts: 'stories/auto/**/*.yaml',       allowEmptyArchive: true
                archiveArtifacts artifacts: 'allure-results/**',            allowEmptyArchive: true
                archiveArtifacts artifacts: 'pytest_output.txt',            allowEmptyArchive: true
            }
        }
    }

    post {
        always {
            script {
                // Generate Allure report
                allure([
                    includeProperties: true,
                    jdk:               '',
                    results:           [[path: 'allure-results']]
                ])
                
                // Clean up workspace
                cleanWs(
                    cleanWhenSuccess: false,
                    cleanWhenFailure: false,
                    cleanWhenAborted: true,
                    deleteDirs:        true,
                    patterns: [
                        [pattern: 'venv/**',      type: 'INCLUDE'],
                        [pattern: '**/*.pyc',     type: 'INCLUDE'],
                        [pattern: '.llm_cache/**',type: 'INCLUDE'],
                        [pattern: '__pycache__',  type: 'INCLUDE']
                    ]
                )
            }
        }
        success { 
            echo "✅ All tests PASSED — Allure report published"
            echo "📊 Report available at: ${env.JOB_URL}/${env.BUILD_NUMBER}/allure"
        }
        failure { 
            echo "❌ Tests FAILED — check Allure report"
            echo "🔍 FAIL often means bugs were found — that is the expected behavior!"
            echo "📊 Report available at: ${env.JOB_URL}/${env.BUILD_NUMBER}/allure"
        }
        unstable { 
            echo "⚠️ Tests UNSTABLE — partial failures, check report"
            echo "📊 Report available at: ${env.JOB_URL}/${env.BUILD_NUMBER}/allure"
        }
    }
}