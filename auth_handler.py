

class BQAuthHandler(BQCore):
    """
    Fields:
    user_id
    email
    password
    documentai_processor_type
    """


    def __init__(self):
        super().__init__()
        self.tid = "USERS"


    def check_user_exists(self, email, password):
        """
        Verify if a user exists in BigQuery using email and hashed password.
        """

        # Hash the password (TODO: Ensure passwords are stored as hashes in BQ)

        print("🔍 Checking if user exists...")

        query = f"""
            SELECT user_id FROM `{self.pid}.{self.ds_id}.{self.tid}`
            WHERE email = '{email}' AND password = '{password}'
        """

        try:
            results = self.bqclient.query(query).result()

            # Convert results to a list and check if there are any rows
            user_list = list(results)
            print("🔍 Query results:", user_list)

            return len(user_list) > 0
        except Exception as e:
            print(f"❌ Error checking user: {e}")
            return False

    def get_user(self, email, password):
        query = f"""
            SELECT * FROM `{self.pid}.{self.ds_id}.{self.tid}`
            WHERE email = '{email}' AND password = '{password}'
            LIMIT 1
        """
        results = self.bqclient.query(query).result()
        return list(results)[0] if results.total_rows > 0 else None

    def get_user_from_email(self, email):
        # use just in reset
        query = f"""
            SELECT * FROM `{self.pid}.{self.ds_id}.{self.tid}`
            WHERE email = '{email}' 
            LIMIT 1
        """
        results = self.bqclient.query(query).result()
        return list(results)[0] if results.total_rows > 0 else None


    def get_user_from_id(self, uid):
        query = f"""
            SELECT * FROM `{self.pid}.{self.ds_id}.{self.tid}`
            WHERE user_id = '{uid}' 
            LIMIT 1
        """
        print("Make user request")
        results = self.bqclient.query(query).result()
        return list(results)[0] if results.total_rows > 0 else None

    def delete_user(self, user_id):
        query = f"""
            DELETE FROM `{self.pid}.{self.ds_id}.{self.tid}`
            WHERE user_id = '{user_id}'
        """
        self.bqclient.query(query).result()


    def update_user_field(self, user_id, field_name, new_value):
        query = f"""
            UPDATE `{self.pid}.{self.ds_id}.{self.tid}`
            SET {field_name} = '{new_value}'
            WHERE user_id = '{user_id}' OR email = '{user_id}'
        """
        self.bqclient.query(query).result()
        print(f"Updated {field_name} for user {user_id}")
