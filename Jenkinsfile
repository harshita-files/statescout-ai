pipeline {
    agent any

    environment {
        CI = "true"
    }

    stages {

        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Install') {
            steps {
                sh 'bun install'
            }
        }

        stage('Lint') {
            steps {
                sh 'bun run lint || true'
            }
        }

        stage('Unit Tests') {
            steps {
                sh 'bun test'
            }
        }

        stage('Build') {
            steps {
                sh 'bun run build || true'
            }
        }

        stage('E2E (stub)') {
            steps {
                sh 'bun run e2e || true'
            }
        }
    }

    post {
        always {
            echo 'Done :)'
        }
        failure {
            echo 'Pipeline failed :('
        }
    }
}