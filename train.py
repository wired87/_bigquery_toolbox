from ggoogle.cloud import aiplatform


def train_vertex_ai_model(project_id, region, dataset, model_name, target_column):
    """
    Trains a Vertex AI AutoML model using a tabular dataset.

    Args:
        project_id (str): Google Cloud project ID.
        region (str): Vertex AI region.
        dataset (aiplatform.TabularDataset): The Vertex AI dataset.
        model_name (str): Name for the trained model.
        target_column (str): Column to predict in the dataset.

    Returns:
        model: The trained Vertex AI model.
    """
    # Initialize Vertex AI client
    aiplatform.init(project=project_id, location=region)

    # Train an AutoML model
    model = aiplatform.TabularAutoMLRegressionTrainingJob(
        display_name=model_name,
        optimization_prediction_type="regression"
    ).run(
        dataset=dataset,
        target_column=target_column,
        model_display_name=model_name,
        budget_milli_node_hours=1000
    )

    print(f"Model trained: {model.resource_name}")
    return model

# Example usage
if __name__ == "__main__":
    project_id = "your_project_id"
    region = "us-central1"
    dataset_name = "my_vertex_ai_dataset"
    target_column = "target_column"
    model_name = "my_automl_model"

    # Load the dataset
    dataset = aiplatform.TabularDataset(dataset_name)

    # Train the model
    train_vertex_ai_model(project_id, region, dataset, model_name, target_column)
