// Jenkinsfile — Phase 4 (MCP + User Stories)

pipeline {

    agent any

    parameters {
        string(
            name:         'TARGET_URLS',
            defaultValue: 'https://www.saucedemo.com',
            description:  'Comma-separated URLs to test in parallel'
        )
        choice(
            name:         'BROWSER',
            choices:      ['chromium', 'firefox', 'webkit'],
            description:  'Browser to use'
        )
        string(
            name:         'MAX_STEPS',
            defaultValue: '1',
            description:  'Exploration steps per page'
        )
        string(
            name:         'MAX_CRAWL_PAGES',
            defaultValue: '3',
            description:  'Max pages to crawl per URL'
        )
        string(
            name:         'MAX_CRAWL_DEPTH',
            defaultValue: '2',
            description:  'Max link depth'
        )
        string(
            name:         'PARALLEL_AGENTS',
            defaultValue: '1',
            description:  'Number of parallel agents'
        )
        string(
            name:         'OLLAMA_MODEL',
            defaultValue: 'llama3',
            description:  'Ollama model'
        )
        choice(
            name:         'STEALTH_MODE',
            choices:      ['true', 'false'],
            description:  'Enable stealth mode'
        )
        string(
            name:         'LOGIN_EMAIL',
            defaultValue: '',
            description:  'Login credentials'
        )
        password(
            name:         'LOGIN_PASSWORD',
            defaultValue: '',
            description:  'Login password'
        )
        booleanParam(
            name:         'STORY_ENABLED',
            defaultValue: false,
            description:  'Auto-generate + run regression stories'
        )
        string(
            name:         'STORIES_DIR',
            defaultValue: 'stories',
            description:  'Directory containing YAML story files'
        )
        booleanParam(
            name:         'SEND_EMAIL',
            defaultValue: false,
            description:  'Send email after run'
        )
    }

    environment {
        TARGET_URLS             = "${params.TARGET_URLS}"
        BROWSER                 = "${params.BROWSER}"
        MAX_STEPS               = "${params.MAX_STEPS}"
        MAX_CRAWL_PAGES         = "${params.MAX_CRAWL_PAGES}"
        MAX_CRAWL_DEPTH         = "${params.MAX_CRAWL_DEPTH}"
        PARALLEL_AGENTS         = "${params.PARALLEL_AGENTS}"
        OLLAMA_MODEL            = "${params.OLLAMA_MODEL}"
        STEALTH_MODE            = "${params.STEALTH_MODE}"
        LOGIN_EMAIL             = "${params.LOGIN_EMAIL}"
        LOGIN_PASSWORD          = "${params.LOGIN_PASSWORD}"
        STORY_ENABLED             = "${params.STORY_ENABLED}"
        STORIES_DIR             = "${params.STORIES_DIR}"
        HEADLESS                = "true"
        OLLAMA_HOST             = "http://localhost:11434"
        OLLAMA_READ_TIMEOUT     = "400"
        OLLAMA_CONNECT_TIMEOUT  = "10"
        OLLAMA_RETRIES          = "2"
        ALLURE_RESULTS_DIR      = "allure-results"
        ALLURE_REPORT_DIR       = "allure-report"
        BUG_REPORTS_DIR         = "bug_reports"
        SCREENSHOTS_DIR         = "screenshots"
        TC_FILE                 = "generated_test_cases.xlsx"
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

        stage('Check Ollama') {
            steps {
                script {
                    if (isUnix()) { sh 'curl -sf http://localhost:11434/api/tags' }
                    else {
                        bat 'curl -sf http://localhost:11434/api/tags > ollama_check.json'
                        bat 'venv\\Scripts\\python.exe check_ollama.py'
                    }
                }
            }
        }

        stage('Run AI Tests') {
            steps {
                script {
                    if (isUnix()) {
                        sh '''
                            . venv/bin/activate
                            pytest run_agents.py \
                                tests/test_agent_results.py \
                                tests/test_bugs.py \
                                tests/test_generated_tcs.py \
                                tests/test_user_stories.py \
                                --alluredir=allure-results \
                                --clean-alluredir \
                                -v --tb=short
                        '''
                    } else {
                        bat 'venv\\Scripts\\pytest.exe run_agents.py tests/test_agent_results.py tests/test_bugs.py tests/test_generated_tcs.py tests/test_user_stories.py --alluredir=allure-results --clean-alluredir -v --tb=short > pytest_output.txt 2>&1'
                    }
                }
            }
        }

        stage('Archive Artifacts') {
            steps {
                archiveArtifacts artifacts: 'screenshots/**/*.png',      allowEmptyArchive: true
                archiveArtifacts artifacts: 'bug_reports/**/*.json',     allowEmptyArchive: true
                archiveArtifacts artifacts: 'generated_test_cases/**/*', allowEmptyArchive: true
                archiveArtifacts artifacts: 'pytest_output.txt',         allowEmptyArchive: true
                archiveArtifacts artifacts: 'allure-results/**',         allowEmptyArchive: true
            }
        }
    }

    post {
        always {
            allure([
                includeProperties: true,
                jdk:               '',
                results:           [[path: 'allure-results']]
            ])
            cleanWs(
                cleanWhenSuccess: false,
                cleanWhenFailure: false,
                cleanWhenAborted: true,
                deleteDirs:        true,
                patterns: [
                    [pattern: 'venv/**', type: 'INCLUDE'],
                    [pattern: '*.pyc',   type: 'INCLUDE']
                ]
            )
        }
        success { echo "✅ All tests PASSED" }
        failure { echo "❌ Tests FAILED — check Allure report" }
        unstable { echo "⚠️ Tests UNSTABLE" }
    }
}
