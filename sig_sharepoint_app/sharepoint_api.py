import json
import logging
import os
import re

from django.conf import settings
from office365.runtime.auth.client_credential import ClientCredential
from office365.sharepoint.client_context import ClientContext
from office365.sharepoint.files.file import File
from office365.sharepoint.folders.folder import Folder
from office365.sharepoint.lists.creation_information import ListCreationInformation
from office365.sharepoint.lists.list import List
from office365.sharepoint.lists.template_type import ListTemplateType

from apps.core.global_constants import SHAREPOINT_URL_PATTERN

from .errors import SharepointError

logger = logging.getLogger("db")


class SharepointClientAccess:
    def __init__(self, site="", server_url="", root_cred_path="", client_id="", client_secret=""):
        self.__site = site
        self.__server_url = server_url
        self.__complete_url = f"{self.__server_url}/sites/{self.__site}"
        if root_cred_path:
            with open(root_cred_path) as file:
                data = json.load(file)
            client_id = data["sites"][site]["username"]
            client_secret = data["sites"][site]["password"]

        elif not client_id or not client_secret:
            raise Exception(
                "Please provide client secrets information as a secrets.json or using the inputs \
                             client_secret and client_id"
            )
        self.ctx, self.web = self.get_sharepoint_ctx(client_id, client_secret)

    @property
    def site(self):
        return self.__site

    @property
    def server_url(self):
        return self.__server_url

    @property
    def complete_url(self):
        return self.__complete_url

    def get_sharepoint_ctx(self, client_id, client_secret):
        cred = ClientCredential(client_id, client_secret)
        url = self.complete_url
        ctx = ClientContext(url).with_credentials(cred)
        web = ctx.web.get().execute_query()
        try:
            ctx.site.get().execute_query()
        except SharepointError:
            logger.error("Unable to execute web queries")

        return ctx, web


class SharepointAPI(SharepointClientAccess):
    def __init__(self, site="", server_url="", root_cred_path="", client_id="", client_secret="") -> None:
        super().__init__(site, server_url, root_cred_path, client_id, client_secret)

    def get_file(self, file_url="") -> File:
        """
        Args:
            file_url (str, optional): Given a sharepoint file url get the object. Defaults to "".

        Returns:
            File: SharepointFile
        """
        file_url = file_url.split(self.server_url)[-1]
        file = self.web.get_file_by_server_relative_path(file_url).get().execute_query()
        return file

    def download_file(self, file_url="", download_path="") -> File:
        """
        Args:
            file_url (str, optional): _description_. Defaults to "".
            download_path (str, optional): _description_. Defaults to "".

        Returns:
            File: SharepointFile
        """
        try:
            with open(download_path, "wb") as file:
                # get the folder
                local_file = self.get_file(file_url).download(file).execute_query()
            logger.info(f"[Ok] file has been downloaded: {download_path}")
            return local_file
        except SharepointError as error:
            logger.error(f"--- Error with download: {error} ---")
            return None

    @classmethod
    def from_url(cls, url: str):
        """
        Generate API instance from a given URL

        Args:
            url (str): a URL to folder or file in a sharepoint site

        Returns:
            self: an instance of SharepointAPI
        """
        try:
            regex = re.compile(SHAREPOINT_URL_PATTERN)
            matches = regex.match(url)
            if matches:
                site = matches.group("site_name")
                server_url = matches.group("server_url")
                return cls(
                    site=site,
                    server_url=server_url,
                    client_id=settings.SHAREPOINT_CLIENT_ID,
                    client_secret=settings.SHAREPOINT_CLIENT_SECRET,
                )
        except SharepointError as error:
            logger.debug(
                "The current location does not contain a site name using the standard site :%s",
                error,
            )
        return cls(
            site=settings.SHAREPOINT_SITE,
            server_url=settings.SHAREPOINT_SERVER_URL,
            client_id=settings.SHAREPOINT_CLIENT_ID,
            client_secret=settings.SHAREPOINT_CLIENT_SECRET,
        )

    def find_folder(self, document_library_name: str, folder_name: str) -> Folder:
        """
        Given a document library name find folder with given folder_name
        Args:
            document_library_name (str): _description_
            folder_name (str): _description_

        Returns:
            Folder: _description_
        """
        result = (
            self.get_document_library_from_name(document_library_name)
            .root_folder.folders.filter(f"Name eq '{folder_name}'")
            .get()
            .execute_query()
        )
        if len(result) == 1:
            return result[0]
        return None

    def create_folder(self, document_library_name: str, folder_name: str) -> Folder:
        """

        Args:
            document_library_name (str): _description_
            folder_name (str): _description_

        Returns:
            Folder: _description_
        """
        folder = self.find_folder(document_library_name, folder_name)
        if not folder:
            folder = (
                self.get_document_library_from_name(document_library_name)
                .root_folder.folders.add(folder_name)
                .execute_query()
            )
        return folder

    def upload_file(
        self,
        document_library_name="",
        root_folder="",
        file_path="",
        file_content=None,
        file_name="",
    ) -> File:
        """
        Currently support only 1 level, i.e., document_library_name/root_folder
        # TODO: support for root_folder in depth greater than 1
        """
        try:
            # path = "../../data/report #123.csv"
            if os.path.exists(file_path):
                if not file_name:
                    file_name = os.path.basename(file_path)
                with open(file_path, "rb") as file_handle:
                    file_content = file_handle.read()
            elif not file_content:
                raise SharepointError("--- Need filename/ file_content when passing bytes to be uploaded ---")

            # uploading commands for sharepoint
            target_folder = self.create_folder(document_library_name, folder_name=root_folder)
            target_file = target_folder.upload_file(file_name, file_content)
            self.ctx.execute_query()

            return target_file

        except SharepointError as error:
            logger.error("Unable to upload file due to error: %s", str(error))
            return None

    def upload_large_file(self, document_libary_name="", root_folder="", file_path="") -> bool:
        """
        Currently support only 1 level, i.e., document_library_name/root_folder
        # TODO: support for root_folder in depth greater than 1
        """
        size_chunk = 1000000
        file_size = os.path.getsize(file_path)
        relative_url = f"{document_libary_name}/{root_folder}"

        try:

            def print_upload_progress(offset):
                print(
                    "Uploaded '{}' bytes from '{}'...[{}%]".format(
                        offset, file_size, round(offset / file_size * 100, 2)
                    )
                )

            target_folder = self.ctx.web.get_folder_by_server_relative_url(relative_url)
            target_file = target_folder.files.create_upload_session(file_path, size_chunk, print_upload_progress)
            self.ctx.execute_query()
            logger.info(f"File {target_file.resource_url} has been uploaded successfully")
            return True
        except SharepointError as error:
            logger.error(" --- Error while uploading: %s ---", error)
            return False

    def get_list_of_files(self, root_folder="") -> list[File]:
        """
        Given a sharepoint document library or a folder within containing objects
        Gets a list of Files inside the root folder.

        Args:
            root_folder (str, optional): _description_. Defaults to "".

        Returns:
            list[File]: list of files in root folder
        """
        try:
            folder = self.ctx.web.lists.get_by_title(root_folder).root_folder.get().execute_query()
            files = folder.files.get().execute_query()
            return files
        except SharepointError as error:
            logger.error(" --- Unable to access folder items: %s ---", error)

    def get_list_of_folders(self, name="") -> list[Folder]:
        """
        Given the sharepoint context, this method returns a list of folders

        Args:
            name (str, optional): _description_. Defaults to "".

        Returns:
            list[Folder]: _description_
        """
        _ = []
        try:
            folders = self.ctx.web.lists.get().execute_query()
            for folder in folders:
                if name:
                    if name.lower() in folder.title.lower():
                        _.append(folder)
                else:
                    _ = folders
                    break
            return _
        except SharepointError as error:
            logger.error(" --- Unable to access folder items: %s ---", error)

    def get_ctx_document_libraries(self) -> list[List]:
        """
        Gets all document libraries
        Returns:
            list[List]
        """
        return self.web.lists.get().execute_query()

    def get_document_library_from_name(self, document_library_name: str):
        """
        Gets a particular document library for a given name
        Args:
            document_library_name (str, optional): _description_. Defaults to "".

        Returns:
            _type_: _description_
        """
        lists = self.web.lists.filter(f"Title eq '{document_library_name}'").get().execute_query()
        return lists[0] if len(lists) == 1 else None

    def create_document_library(self, document_library_name: str, description: str = "") -> List:
        """
        Creates a document library if none present and returns the object
        Args:
            document_library_name (str, optional): _description_. Defaults to "".

        """
        element = self.get_document_library_from_name(document_library_name)
        if not element:
            list_properties = ListCreationInformation(
                document_library_name, description, ListTemplateType.DocumentLibrary
            )
            element = self.web.lists.add(list_properties).execute_query()
        return element

    def delete_document_library(self, document_library_name: str):
        """
        For a given document library name, delete it if it exists
        Args:
            document_library_name (str): _description_
        """
        element = self.get_document_library_from_name(document_library_name)
        if element:
            element.delete_object().execute_query()
