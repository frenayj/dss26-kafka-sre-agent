terraform {
  required_version = ">= 1.6, < 2.0"

  required_providers {
    datadog = {
      source  = "DataDog/datadog"
      version = "~> 3.46"
    }
  }

  backend "s3" {
    bucket         = "dss26-tfstate-cards-prod"
    key            = "fraud-decisioning-svc/monitoring.tfstate"
    region         = "eu-west-1"
    dynamodb_table = "dss26-tfstate-locks"
    encrypt        = true
  }
}

# DD_API_KEY and DD_APP_KEY come from the CI environment.
provider "datadog" {
  api_url = "https://api.datadoghq.eu/"
}
